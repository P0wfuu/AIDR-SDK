# 🛡️ AIDR-SDK

<p align="center">
  <a href="https://github.com/P0wfuu/AIDR-SDK">
    <img src="https://img.shields.io/badge/Repo-AIDR--SDK-0ea5e9?style=for-the-badge&logo=github&logoColor=white" alt="Repo" />
  </a>
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-16a34a?style=for-the-badge&logo=open-source-initiative&logoColor=white" alt="License" />
  </a>
</p>

<p align="center">
  <strong>English</strong> |
  <a href="./README_CN.md">简体中文</a>
</p>

<p align="center">
  <strong>AIDR-SDK: Runtime access control for tool-use LLM agents</strong>
</p>

<p align="center">
  Declarative policy enforcement, provenance-aware decisions, soft-block
  obligations, and human-in-the-loop safety for tool invocations across
  every mainstream agent framework — including Claude Agent SDK.
</p>

> [!IMPORTANT]
> This project is in active development. It originated as a fork of
> [AgentGuard](https://github.com/WhitzardAgent/AgentGuard) (MIT, Fudan
> University SecSys Lab) and is being adapted for production use. See
> `LICENSE` for the upstream copyright.

AIDR-SDK is an attribute-based access control framework for agent tool calls
that sits between an LLM-based planning engine and the tools it invokes.
Before each tool call is executed, and again after it completes, AIDR-SDK
evaluates the agent's behavior against declarative policies to decide whether
the action should proceed as-is, be blocked, be routed for human review, or
have its parameters rewritten (REDACT / DEGRADE).

The framework targets the technical areas highlighted in Anthropic's
[Zero Trust for AI Agents](https://claude.com/blog/zero-trust-for-ai-agents):
access control & privilege management, observability & auditing, and
behavioral monitoring & response.

![Architecture overview](./docs/figs/positioning.png)

## ✨ Features

### 1. Rich Policy Expressiveness

Policies are written in a standalone DSL, not hard-coded checks buried in
business logic. A policy can reference the principal's identity, tool
metadata, tool arguments, target addresses, session history, and call-chain
context.

#### Arithmetic & Logical Expressions

Policy conditions support numeric comparisons, set membership, regex,
substring matching, and arbitrary `AND` / `OR` / `NOT` composition.

#### Cross-Tool Policies

`TRACE` clauses and session-history functions express behaviors such as
"read from a database, then send email," "read a sensitive file, then upload
it to an external HTTP endpoint," or "external input eventually flows into a
shell command," rather than relying solely on the current tool's arguments.

#### Multi-Phase Intervention

Policies can apply at the pre-execution `requested` phase, the post-execution
`completed` phase, or the failure `failed` phase.

#### Diverse Policy Decisions

When a rule matches, it can return `ALLOW`, `DENY`, `HUMAN_CHECK`, or
`LLM_CHECK`, plus obligations (`REDACT`, `RATE_LIMIT`, `AUDIT`,
`REQUIRE_TARGET_IN`, `DEGRADE`). Policies are therefore not limited to
binary allow/deny outcomes.

#### Subject & Object Labels

Policies enforce differentiated controls based on agent (subject) and tool
(object) attributes. Agents declare identity (`agent_id`, `session_id`,
`role`, `trust_level`, `scope`). Tools declare static labels (`boundary`,
`sensitivity`, `integrity`, `tags`) at registration time.

### 2. Seamless Integration with Agent Frameworks

AIDR-SDK sits between the LLM-based planning engine and tools without
interfering with planning, reasoning, or orchestration. Adapters are provided
for the following frameworks:

- [LangChain / LangGraph](https://github.com/langchain-ai/langchain)
- [AutoGen](https://github.com/microsoft/autogen)
- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) *(new in this fork — see [docs/claude-agent-sdk.md](./docs/claude-agent-sdk.md))*
- [Dify](https://github.com/langgenius/dify) *(stream-event observation; coarse-grained)*
- OpenClaw *(reference implementation)*

For frameworks not yet supported, a `BaseAdapter` extension point makes
custom integration straightforward. See
[docs/agent-sdk-landscape.md](./docs/agent-sdk-landscape.md) for the full
landscape of agent SDKs across Python, TypeScript, Java, Go, and Rust, and
[docs/cross-language-roadmap.md](./docs/cross-language-roadmap.md) for the
plan to make AIDR-SDK accessible from non-Python runtimes.

### 3. Visual Policy Configuration & Audit

A web console for managing agents ships with the project. The visual interface
lets operators configure policies through forms and dropdowns instead of
hand-writing DSL. The runtime dashboard displays agent health, recent traffic,
pending approval requests, and audit records.

### 4. Cluster Management

A centralized control-plane architecture governs distributed agent processes.
Agents can be deployed across multiple nodes; policy configuration and runtime
monitoring are managed centrally through the control server.

## 🚀 Quick Start

### 1. Write Access Control Policies and Start the Control Server

> Docker must be installed first.

Choose a host to serve as the control server, then clone the repo:

```bash
git clone git@github.com:P0wfuu/AIDR-SDK.git
cd AIDR-SDK
```

Create an access control policy:

```bash
mkdir -p rules

cat <<EOF > rules/block_email_send.rules
RULE: block_untrusted_email_send
TRACE: Retriever -> ...? -> Mailer
CONDITION: Retriever.name == "retrieve_doc"
           AND Mailer.name == "send_email_to"
           AND Retriever.id == 0
           AND Mailer.addr != "admin@example.com"
POLICY: DENY
Severity: high
Category: data_exfiltration
Reason: "Low-trust principal cannot send document 0 to non-admin recipients"
EOF
```

Configure environment variables (optional — defaults are sufficient for a
local trial):

```bash
cp .env.example .env
vi .env
```

Start the control server:

```bash
./scripts/start.sh -d
```

- Control server: `http://localhost:38080`
- Web UI: `http://localhost:8080`

### 2. Agent-Side Setup

On the agent host:

```bash
git clone git@github.com:P0wfuu/AIDR-SDK.git
cd AIDR-SDK
pip install -e .
```

#### LangChain example

```python
from langchain.agents import create_agent
from langchain.tools import tool
from agentguard import Guard, Principal

@tool
def retrieve_doc(id: int) -> str:
    return f"DOC#{id}: mocked document body."

@tool
def send_email_to(doc: str, addr: str) -> str:
    return f"Email sent to {addr}: {doc}"

agent = create_agent(model=..., tools=[retrieve_doc, send_email_to])

guard = Guard(remote_url="http://<Control Server IP>:38080",
              mode="enforce", fail_open=False)
guard.start(principal=Principal(
    agent_id="langchain-demo",
    session_id="langchain-session",
    role="default", trust_level=1,
))
guard.attach_langchain(agent)
```

#### Claude Agent SDK example (new)

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from agentguard import Guard, Principal

options = ClaudeAgentOptions(
    mcp_servers={"docs": my_sdk_mcp_server},
    allowed_tools=["mcp__docs__retrieve_doc", "Bash", "Read"],
)

guard = Guard()
guard.start(principal=Principal(
    agent_id="claude-cli", session_id="s1",
    role="default", trust_level=1,
))
guard.attach_claude_agent(options)   # mutates options in place

async with ClaudeSDKClient(options=options) as client:
    await client.query("...")
```

Both the user-defined SDK MCP tools **and** the Claude Code built-in tools
(`Bash`, `Read`, `Write`, `Edit`, `WebFetch`, ...) are governed. Full guide:
[docs/claude-agent-sdk.md](./docs/claude-agent-sdk.md).

### 3. Manage the Agent's Runtime with UI

Inspect runtime status and policy enforcement audit logs through the web UI.
The UI also supports visual policy configuration with hot-reload.

For further deployment details, see [docs/](./docs/).

## 🏆 Advantages over Existing Frameworks

Defenses for agent security mainly fall into two categories:
**malicious-intent detection at the model layer** and **tool-call behavior
interception**. The former strengthens the underlying LLM through fine-tuning
or detects unsafe intent via reasoning analysis; the latter enforces
predefined security policies at tool invocation time based on call traces,
arguments, and runtime context.

Model fine-tuning is expensive and many models don't expose a complete
reasoning trace. AIDR-SDK focuses on the tool-call behavior layer: it doesn't
require changing the underlying model, and places security controls around
what the agent actually does, making it easier to integrate into existing
agent stacks and more practical for production deployment.

![Advantages over existing frameworks](./docs/figs/comparison_en.png)

## 🏗️ Architecture

<p align="center">
  <img src="./docs/figs/overview.png" alt="AIDR-SDK architecture" width="50%" />
</p>

- **Client**: With minimal code modifications, the client integrates into
  agent frameworks. It monitors every tool call, forwards relevant context to
  the server, and enforces the server's policy decisions.
- **Server**: Receives information from clients, evaluates agent actions
  against policies, produces policy decisions, and sends them back to
  clients. It also monitors agent status for administrative auditing.

## 🗺️ Documentation

- [`docs/claude-agent-sdk.md`](./docs/claude-agent-sdk.md) — Claude Agent SDK adapter (new)
- [`docs/agent-sdk-landscape.md`](./docs/agent-sdk-landscape.md) — survey of Python / Node / Java / Go / Rust agent frameworks
- [`docs/cross-language-roadmap.md`](./docs/cross-language-roadmap.md) — strategy for non-Python AIDR-SDK clients
- [`docs/en/`](./docs/en) and [`docs/zh/`](./docs/zh) — concepts, DSL reference, adapter guides (inherited from upstream, partially updated)

## 🎯 Roadmap

- Production hardening: persistent provenance graph backend, distributed
  rate-limit / approval state
- Cross-language clients: TypeScript / Go thin HTTP SDK (see
  [cross-language-roadmap](./docs/cross-language-roadmap.md))
- mTLS / SPIFFE-based principal authentication
- OpenTelemetry exporter for telemetry
- Differential dry-run for new rule deployment
- Per-sink fail-open / fail-close policy

## 🙏 Upstream Credits

AIDR-SDK builds on [AgentGuard](https://github.com/WhitzardAgent/AgentGuard)
by the System Software and Security Lab at Fudan University. The original
design of the DSL, the policy engine, the runtime, and the framework adapters
was contributed by the AgentGuard team. See `LICENSE` for the upstream MIT
copyright notice.

## 📜 License

This project is licensed under the [MIT License](./LICENSE).
