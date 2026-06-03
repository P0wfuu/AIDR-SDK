"""Adapter for Claude Agent SDK (Python).

Two interception layers:

1. **SDK MCP server tools** (user-defined via ``@tool`` + ``create_sdk_mcp_server``)
   are wrapped at registration time. Each tool callable is replaced with a guarded
   variant that goes through ``guard.pipeline.handle_attempt`` before/after the
   real call. This matches how the LangChain / AutoGen / OpenAI Agents adapters
   work.

2. **Built-in Claude Code tools** (Bash, Read, Write, Edit, WebFetch, ...) cannot
   be patched at registration time because they live inside the Claude Code CLI
   process, not in the user's Python code. We intercept them via the
   ``PreToolUse`` hook injected into ``ClaudeAgentOptions.hooks``. The hook
   translates each tool invocation into a ``RuntimeEvent``, runs it through the
   Guard pipeline, and maps the resulting ``Decision`` onto Claude Agent SDK's
   hook output schema (``permissionDecision`` / ``modifiedToolInput``).

Usage::

    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient, tool, create_sdk_mcp_server
    from agentguard import Guard, Principal

    @tool("greet", "Greet a user", {"name": str})
    async def greet(args):
        return {"content": [{"type": "text", "text": f"hi {args['name']}"}]}

    server = create_sdk_mcp_server(name="my-tools", version="1.0.0", tools=[greet])

    options = ClaudeAgentOptions(
        mcp_servers={"my-tools": server},
        allowed_tools=["mcp__my-tools__greet", "Bash", "Read"],
    )

    guard = Guard(policy_source="rules/")
    guard.start(principal=Principal(agent_id="claude-cli", session_id="s1",
                                    role="default", trust_level=1))
    guard.attach_claude_agent(options)   # mutates options in place

    async with ClaudeSDKClient(options=options) as client:
        await client.query("...")
"""

from __future__ import annotations

import inspect
import logging
from typing import Any

from agentguard.models.decisions import Action, Decision
from agentguard.models.errors import DecisionDenied, HumanApprovalPending
from agentguard.models.events import EventType, RuntimeEvent, ToolCall
from agentguard.sdk.adapters.base import BaseAdapter
from agentguard.sdk.context import current_session

log = logging.getLogger(__name__)


# Claude Code built-in tools that are commonly governed.
# These names follow the Claude Agent SDK / Claude Code tool naming convention.
_BUILTIN_TOOLS = (
    "Bash",
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "WebFetch",
    "WebSearch",
    "Glob",
    "Grep",
    "Task",
    "TodoWrite",
)


class ClaudeAgentAdapter(BaseAdapter):
    """Attach AgentGuard to a Claude Agent SDK setup.

    The target ``framework_obj`` is a ``ClaudeAgentOptions`` instance. This adapter
    mutates two of its fields:

    * ``mcp_servers``: for each SDK MCP server, every registered tool callable is
      wrapped with a guarded variant.
    * ``hooks``: a ``PreToolUse`` hook covering Claude Code built-in tools is
      appended to whatever the user already registered.
    """

    builtin_tools: tuple[str, ...] = _BUILTIN_TOOLS

    def install(self, framework_obj: Any) -> None:
        self._wrap_sdk_mcp_tools(framework_obj)
        self._inject_pretooluse_hook(framework_obj)

    # ------------------------------------------------------------------
    # (1) wrap SDK MCP server tools (user @tool functions)
    # ------------------------------------------------------------------

    def _wrap_sdk_mcp_tools(self, options: Any) -> None:
        mcp_servers = getattr(options, "mcp_servers", None)
        if not isinstance(mcp_servers, dict):
            log.debug("ClaudeAgentAdapter: no mcp_servers on options; skipping MCP wrap.")
            return
        for server_key, server in mcp_servers.items():
            tools = self._extract_server_tools(server)
            if not tools:
                log.debug(
                    "ClaudeAgentAdapter: server %r has no extractable tools.", server_key
                )
                continue
            for tool_obj in tools:
                self._patch_mcp_tool(server_key, tool_obj)

    @staticmethod
    def _extract_server_tools(server: Any) -> list[Any]:
        """Best-effort extraction of registered tool objects from an SDK MCP server.

        ``create_sdk_mcp_server(tools=[...])`` is the user-facing constructor.
        The internal attribute name has varied across SDK versions, so we probe
        a few likely names.
        """
        for attr in ("_tools", "tools", "_registered_tools", "_tool_handlers"):
            tools = getattr(server, attr, None)
            if tools is None:
                continue
            if isinstance(tools, dict):
                return list(tools.values())
            if isinstance(tools, (list, tuple)):
                return list(tools)
        return []

    def _patch_mcp_tool(self, server_key: str, tool_obj: Any) -> None:
        name = (
            getattr(tool_obj, "name", None)
            or getattr(tool_obj, "tool_name", None)
            or getattr(tool_obj, "__name__", None)
        )
        if not name:
            log.debug("ClaudeAgentAdapter: tool object has no resolvable name; skipping.")
            return

        # Qualified name as Claude sees it on the wire.
        qualified = f"mcp__{server_key}__{name}"

        # Tool object stores its callable under one of several attribute names
        # depending on SDK version.
        for attr in ("handler", "fn", "func", "callback", "implementation"):
            fn = getattr(tool_obj, attr, None)
            if not callable(fn) or getattr(fn, "__agentguard__", None):
                continue
            wrapped = self._wrap_mcp_callable(qualified, fn)
            try:
                object.__setattr__(tool_obj, attr, wrapped)
            except (AttributeError, TypeError):
                try:
                    setattr(tool_obj, attr, wrapped)
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning(
                        "ClaudeAgentAdapter: failed to patch %s.%s: %s",
                        qualified,
                        attr,
                        exc,
                    )
                    return
            self.guard._record_tool_registration(qualified, wrapped)
            log.debug(
                "ClaudeAgentAdapter: wrapped MCP tool %s (via attr %r).",
                qualified,
                attr,
            )
            return

    def _wrap_mcp_callable(self, qualified_name: str, fn: Any) -> Any:
        """Wrap a single @tool callable.

        Claude Agent SDK ``@tool`` callables have signature
        ``async def f(args: dict) -> dict`` where the return value is an MCP
        content envelope ``{"content": [{"type": "text", "text": str}, ...]}``.

        We cannot reuse ``wrappers.wrap_tool`` directly because it inspects the
        callable's per-parameter signature; the MCP wrapper has a single
        ``args`` dict. So we hand-roll a thin wrapper that builds the
        ``RuntimeEvent`` from the ``args`` dict and applies the Decision.
        """

        pipeline = self.pipeline
        adapter = self

        async def guarded(args):  # type: ignore[no-untyped-def]
            arg_dict: dict[str, Any] = (
                dict(args) if isinstance(args, dict) else {"raw_input": args}
            )
            event = adapter._build_event(qualified_name, arg_dict)

            decision = pipeline.handle_attempt(event)
            adapter._apply_decision_or_raise(decision, qualified_name)

            # DEGRADE / REDACT may have rewritten args; pick them up.
            rewritten = adapter._collect_rewritten_args(decision)
            call_args = rewritten if rewritten is not None else arg_dict

            try:
                if inspect.iscoroutinefunction(fn):
                    result = await fn(call_args)
                else:
                    result = fn(call_args)
            except Exception as exc:
                adapter._dispatch_failed(event, exc)
                raise

            adapter._dispatch_completed(event, result)
            return result

        guarded.__agentguard__ = True  # type: ignore[attr-defined]
        return guarded

    # ------------------------------------------------------------------
    # (2) inject PreToolUse hook for built-in Claude Code tools
    # ------------------------------------------------------------------

    def _inject_pretooluse_hook(self, options: Any) -> None:
        try:
            from claude_agent_sdk import HookMatcher  # type: ignore
        except ImportError:
            log.info(
                "ClaudeAgentAdapter: claude_agent_sdk not installed; "
                "skipping PreToolUse hook injection."
            )
            return

        hooks = getattr(options, "hooks", None)
        if hooks is None:
            hooks = {}
            try:
                object.__setattr__(options, "hooks", hooks)
            except (AttributeError, TypeError):
                try:
                    options.hooks = hooks
                except Exception:
                    log.warning(
                        "ClaudeAgentAdapter: could not set options.hooks; "
                        "built-in tool governance disabled."
                    )
                    return

        matcher_pattern = "|".join(self.builtin_tools)
        guard_hook = self._build_pretooluse_hook()

        existing = hooks.get("PreToolUse") or []
        existing = list(existing)
        existing.append(HookMatcher(matcher=matcher_pattern, hooks=[guard_hook]))
        hooks["PreToolUse"] = existing
        log.debug(
            "ClaudeAgentAdapter: PreToolUse hook installed for tools: %s",
            matcher_pattern,
        )

    def _build_pretooluse_hook(self):
        """Build the PreToolUse hook callable.

        Claude Agent SDK PreToolUse hook signature:
            ``async def hook(input_data: dict, tool_use_id: str, context) -> dict``
        where ``input_data`` contains ``tool_name`` and ``tool_input``.

        Return shape (per SDK docs):
            ``{"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                      "permissionDecision": "allow"|"deny"|"ask",
                                      "permissionDecisionReason": str,
                                      "modifiedToolInput": dict?}}``
        """
        adapter = self
        pipeline = self.pipeline

        async def guard_pretooluse(input_data, tool_use_id, context):  # type: ignore[no-untyped-def]
            tool_name = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input") or {}
            if not isinstance(tool_input, dict):
                tool_input = {"raw_input": tool_input}

            event = adapter._build_event(tool_name, tool_input)

            try:
                decision = pipeline.handle_attempt(event)
            except Exception as exc:
                log.warning(
                    "ClaudeAgentAdapter hook error for %s (fail-open): %s",
                    tool_name,
                    exc,
                )
                return {}

            action = decision.action
            reason = decision.reason or " ".join(decision.matched_rules) or "AgentGuard policy"

            if action is Action.DENY:
                return _hook_output("deny", reason)

            if action in (Action.HUMAN_CHECK, Action.LLM_CHECK):
                # Claude Code's PreToolUse hook is synchronous-return only;
                # there's no native "wait for human approval" channel here.
                # Map to "ask" so Claude Code shows the permission prompt;
                # the actual approval still has to come from the operator.
                return _hook_output("ask", f"AgentGuard {action.value}: {reason}")

            # DEGRADE or ALLOW with rewrites: surface modifiedToolInput so
            # Claude Code calls the tool with sanitised args.
            rewritten = adapter._collect_rewritten_args(decision)
            if rewritten is not None and rewritten != tool_input:
                return _hook_output(
                    "allow",
                    reason or "AgentGuard rewrote parameters",
                    modified_tool_input=rewritten,
                )

            # ALLOW with no obligations → empty dict means "no change, proceed"
            return {}

        return guard_pretooluse

    # ------------------------------------------------------------------
    # shared helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_event(tool_name: str, tool_input: dict[str, Any]) -> RuntimeEvent:
        session = current_session()
        principal = session.principal if session else None
        if principal is None:
            # Defensive default; in practice guard.start() should have set this.
            from agentguard.models.events import Principal

            principal = Principal(
                agent_id="claude-agent-sdk",
                session_id=getattr(session, "session_id", "claude-agent-session"),
            )

        tc = ToolCall(
            tool_name=tool_name,
            args=tool_input,
            syntax=list(tool_input.keys()),
        )
        return RuntimeEvent(
            event_type=EventType.TOOL_CALL_REQUESTED,
            principal=principal,
            tool_call=tc,
            goal=getattr(session, "goal", None) if session else None,
            scope=list(getattr(session, "scope", []) or []) if session else [],
        )

    @staticmethod
    def _apply_decision_or_raise(decision: Decision, tool_name: str) -> None:
        if decision.action is Action.DENY:
            raise DecisionDenied(decision.reason or tool_name)
        if decision.action in (Action.HUMAN_CHECK, Action.LLM_CHECK):
            # Surface as HumanApprovalPending so the caller can poll/await.
            raise HumanApprovalPending(
                ticket_id=(decision.matched_rules[0] if decision.matched_rules else tool_name)
            )

    @staticmethod
    def _collect_rewritten_args(decision: Decision) -> dict[str, Any] | None:
        """Extract REDACT / DEGRADE rewrites from a Decision's obligations.

        We look for obligations whose ``kind`` rewrites tool input:
        ``mask_fields``, ``rewrite_tool`` (for args portion). The exact applied
        rewrite normally happens inside the Enforcer; here we just surface the
        intended values for the Claude Code hook's ``modifiedToolInput`` field.
        """
        rewritten: dict[str, Any] | None = None
        for ob in decision.obligations:
            if ob.kind == "mask_fields":
                fields = ob.params.get("fields") or ob.params.get("field") or []
                if isinstance(fields, str):
                    fields = [fields]
                if not fields:
                    continue
                rewritten = dict(rewritten or {})
                for f in fields:
                    rewritten[str(f)] = "[REDACTED]"
            elif ob.kind == "rewrite_tool":
                new_args = ob.params.get("args")
                if isinstance(new_args, dict):
                    rewritten = dict(new_args)
        return rewritten

    def _dispatch_completed(self, event: RuntimeEvent, result: Any) -> None:
        try:
            result_str = str(result)[:4096]
        except Exception:
            result_str = "<unserialisable>"
        completed_tc = (event.tool_call.model_copy(update={"result": result_str})
                        if event.tool_call else None)
        completed = event.model_copy(update={
            "event_type": EventType.TOOL_CALL_COMPLETED,
            "tool_call": completed_tc,
            "result": result_str,
        })
        try:
            self.pipeline.handle_result(completed)
        except Exception as exc:
            log.debug("ClaudeAgentAdapter: handle_result failed: %s", exc)

    def _dispatch_failed(self, event: RuntimeEvent, exc: BaseException) -> None:
        failed = event.model_copy(update={
            "event_type": EventType.TOOL_CALL_FAILED,
            "extra": {**(event.extra or {}), "error": repr(exc)[:512]},
        })
        try:
            self.pipeline.handle_result(failed)
        except Exception as inner:
            log.debug("ClaudeAgentAdapter: handle_result(failed) failed: %s", inner)


def _hook_output(
    permission_decision: str,
    reason: str,
    *,
    modified_tool_input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": permission_decision,
            "permissionDecisionReason": reason,
        }
    }
    if modified_tool_input is not None:
        payload["hookSpecificOutput"]["modifiedToolInput"] = modified_tool_input
    return payload
