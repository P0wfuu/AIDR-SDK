"""Claude Agent SDK + AgentGuard demo.

What this shows
---------------
1. A user-defined SDK MCP tool (``retrieve_doc``) is wrapped at registration
   time. AgentGuard sees its calls as ``mcp__docs__retrieve_doc`` events.
2. A Claude Code built-in tool (``Bash``) is governed via the PreToolUse hook.
3. A simple rule denies ``rm -rf`` style destructive commands and redacts the
   ``addr`` argument of ``send_email`` outside the admin allowlist.

How to run
----------
::

    pip install claude-agent-sdk
    export ANTHROPIC_API_KEY=...
    python -m agentguard.examples.claude_agent_demo.demo

The demo uses the local in-process Guard (no remote server required).
"""

from __future__ import annotations

import asyncio
import textwrap

from agentguard import Guard, Principal


_RULES = textwrap.dedent("""
    RULE: deny_destructive_bash
    ON: tool_call.requested(Bash)
    CONDITION: tool.command MATCHES ".*(rm\\s+-rf|mkfs|dd\\s+if=).*"
    POLICY: DENY
    Severity: critical
    Category: shell
    Reason: "destructive shell command blocked by AgentGuard"

    RULE: redact_send_email_address
    ON: tool_call.requested(mcp__docs__send_email)
    CONDITION: tool.addr NOT IN {"admin@example.com"}
    POLICY: ALLOW WITH REDACT(fields={"addr"}),
                   AUDIT(severity="medium", category="email_egress")
""").strip()


async def _main() -> None:
    # claude_agent_sdk is an optional dependency; import lazily so the demo
    # file is at least importable in environments without it.
    from claude_agent_sdk import (
        ClaudeAgentOptions,
        ClaudeSDKClient,
        create_sdk_mcp_server,
        tool,
    )

    @tool("retrieve_doc", "Retrieve a document by id", {"id": int})
    async def retrieve_doc(args):
        return {
            "content": [{"type": "text", "text": f"DOC#{args['id']}: secret payload"}]
        }

    @tool("send_email", "Send an email", {"addr": str, "body": str})
    async def send_email(args):
        return {
            "content": [
                {"type": "text", "text": f"sent {args['body']!r} to {args['addr']}"}
            ]
        }

    docs_server = create_sdk_mcp_server(
        name="docs",
        version="1.0.0",
        tools=[retrieve_doc, send_email],
    )

    options = ClaudeAgentOptions(
        mcp_servers={"docs": docs_server},
        allowed_tools=[
            "mcp__docs__retrieve_doc",
            "mcp__docs__send_email",
            "Bash",
            "Read",
        ],
    )

    guard = Guard()  # in-process; no remote control server needed
    guard.add_rules_from_text(_RULES)
    guard.start(
        principal=Principal(
            agent_id="claude-agent-demo",
            session_id="s-claude-demo",
            role="default",
            trust_level=1,
        ),
        goal="claude agent demo",
    )

    # The single call that wires AgentGuard into Claude Agent SDK.
    guard.attach_claude_agent(options)

    try:
        async with ClaudeSDKClient(options=options) as client:
            await client.query(
                "Retrieve document id=0 and email it to alice@example.com."
            )
            async for msg in client.receive_response():
                print(msg)
    finally:
        guard.close()


if __name__ == "__main__":
    asyncio.run(_main())
