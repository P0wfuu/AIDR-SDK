# 🛡️ AIDR-SDK

<p align="center">
  <a href="https://github.com/P0wfuu/AIDR-SDK">
    <img src="https://img.shields.io/badge/%E4%BB%93%E5%BA%93-AIDR--SDK-0ea5e9?style=for-the-badge&logo=github&logoColor=white" alt="仓库" />
  </a>
  <a href="./LICENSE">
    <img src="https://img.shields.io/badge/%E8%AE%B8%E5%8F%AF%E8%AF%81-MIT-16a34a?style=for-the-badge&logo=open-source-initiative&logoColor=white" alt="许可证" />
  </a>
</p>

<p align="center">
  <a href="./README.md">English</a> |
  <strong>简体中文</strong>
</p>

<p align="center">
  <strong>AIDR-SDK：面向 LLM Agent 工具调用的运行时访问控制框架</strong>
</p>

<p align="center">
  声明式策略 · 数据流溯源 · 软处置（REDACT / DEGRADE）· 人工/LLM 复核 ·
  覆盖主流 Agent 框架（含 Claude Agent SDK）
</p>

> [!IMPORTANT]
> 本项目处于活跃开发阶段。它衍生自 [AgentGuard](https://github.com/WhitzardAgent/AgentGuard)
> （MIT 许可，复旦大学系统软件与安全实验室），正在为生产环境落地做适配。
> 上游版权声明见 `LICENSE`。

AIDR-SDK 是一个面向 Agent 工具调用的基于属性的访问控制框架，作用于 LLM 规划
引擎与真实工具之间。在每一次工具调用真正执行之前以及执行结束之后，AIDR-SDK
依据声明式策略评估 Agent 行为，判断是否放行、阻断、转人工复核，或对参数做
脱敏 / 降级改写（REDACT / DEGRADE）。

整个框架覆盖 Anthropic [Zero Trust for AI Agents](https://claude.com/blog/zero-trust-for-ai-agents)
强调的三类能力：访问控制与权限管理、可观测性与审计、行为监控与响应。

![架构定位](./docs/figs/positioning.png)

## ✨ 功能特点

### 1. 丰富的策略表达能力

策略使用独立 DSL 描述，而非散落在业务代码里的硬编码检查。一条规则可以引用
身份属性、工具元数据、工具参数、目标地址、会话历史、调用链上下文。

#### 算术与逻辑表达式

策略条件支持数值比较、集合判断、正则匹配、子串匹配，以及 `AND` / `OR` /
`NOT` 任意组合。

#### 跨工具策略

`TRACE` 子句和会话历史函数可以表达"先查库再发邮件"、"读敏感文件再上传外部
HTTP"、"外部输入最终流到 shell 命令"等组合行为，而不只看当前一次调用的参数。

#### 多阶段拦截

策略可作用于执行前（`requested`）、执行后（`completed`）、失败时（`failed`）
三个阶段。

#### 多种决策类型

匹配后可返回 `ALLOW` / `DENY` / `HUMAN_CHECK` / `LLM_CHECK` 四种决策，
配合义务 (`REDACT` / `RATE_LIMIT` / `AUDIT` / `REQUIRE_TARGET_IN` / `DEGRADE`)。

#### 主体与客体标签

策略可基于 Agent（主体）和工具（客体）属性做差异化控制。Agent 声明身份
（`agent_id` / `session_id` / `role` / `trust_level` / `scope`），工具在
注册时声明静态标签（`boundary` / `sensitivity` / `integrity` / `tags`）。

### 2. 无缝集成主流 Agent 框架

AIDR-SDK 位于 LLM 规划引擎与工具之间，不干预 Agent 的规划、推理或任务编排。
目前内置如下框架的适配器：

- [LangChain / LangGraph](https://github.com/langchain-ai/langchain)
- [AutoGen](https://github.com/microsoft/autogen)
- [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) *（本 fork 新增 — 详见 [docs/claude-agent-sdk.md](./docs/claude-agent-sdk.md)）*
- [Dify](https://github.com/langgenius/dify) *（流式事件观察，粒度粗）*
- OpenClaw *（参考实现）*

对于尚未支持的框架，可通过 `BaseAdapter` 扩展点写自定义适配器。Python /
TypeScript / Java / Go / Rust 生态全景与跨语言治理路径，分别见
[docs/agent-sdk-landscape.md](./docs/agent-sdk-landscape.md) 和
[docs/cross-language-roadmap.md](./docs/cross-language-roadmap.md)。

### 3. 可视化策略配置与审计

随项目附带 Web 控制台。可视化界面让运营人员通过表单和下拉选项配置策略，
不需要手写 DSL。运行时仪表盘展示 Agent 健康度、近期流量、待审工单、审计记录。

### 4. 集群管理

中心化控制面架构治理分布式 Agent 进程：Agent 可分布部署在网络多个节点，
策略配置和运行时监控通过控制服务集中管理。

## 🚀 快速开始

### 1. 编写访问控制策略并启动控制服务

> 需要先安装 Docker。

```bash
git clone git@github.com:P0wfuu/AIDR-SDK.git
cd AIDR-SDK
```

创建一条策略：

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
Reason: "低信任 Agent 不能把文档 0 发给非管理员"
EOF
```

可选：配置环境变量后启动：

```bash
cp .env.example .env
./scripts/start.sh -d
```

- 控制面：`http://localhost:38080`
- Web UI：`http://localhost:8080`

### 2. Agent 端接入

```bash
git clone git@github.com:P0wfuu/AIDR-SDK.git
cd AIDR-SDK
pip install -e .
```

#### LangChain 示例

```python
from langchain.agents import create_agent
from langchain.tools import tool
from agentguard import Guard, Principal

@tool
def retrieve_doc(id: int) -> str:
    return f"DOC#{id}: 模拟文档"

@tool
def send_email_to(doc: str, addr: str) -> str:
    return f"已发往 {addr}：{doc}"

agent = create_agent(model=..., tools=[retrieve_doc, send_email_to])
guard = Guard(remote_url="http://<控制面 IP>:38080", mode="enforce", fail_open=False)
guard.start(principal=Principal(
    agent_id="langchain-demo", session_id="s1",
    role="default", trust_level=1,
))
guard.attach_langchain(agent)
```

#### Claude Agent SDK 示例（新增）

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
guard.attach_claude_agent(options)   # 原地修改 options

async with ClaudeSDKClient(options=options) as client:
    await client.query("...")
```

用户自定义的 SDK MCP 工具 **以及** Claude Code 内置工具（`Bash` / `Read` /
`Write` / `Edit` / `WebFetch` 等）都会被治理。完整说明见
[docs/claude-agent-sdk.md](./docs/claude-agent-sdk.md)。

### 3. 用 UI 管理 Agent 运行时

通过 Web UI 查看 Agent 运行状态与策略执行审计日志。UI 也支持可视化策略配置
和热加载。

更多部署细节见 [docs/](./docs/)。

## 🏆 相对现有方案的差异

业界对 Agent 安全的防御主要分两类：**模型层的恶意意图检测**，以及
**工具调用层的行为拦截**。前者通过微调或推理链分析提升底层 LLM 的安全性；
后者在工具调用时基于调用轨迹、参数、运行时上下文执行预定义策略。

模型微调成本高且许多模型不暴露完整推理链。AIDR-SDK 聚焦于工具调用行为层 ——
不需要改底层模型，而是围绕 Agent 真正做的事情布置安全控制，更易集成进现有
Agent 栈，更适合生产环境部署。

![相对现有方案的差异](./docs/figs/comparison_en.png)

## 🏗️ 架构

<p align="center">
  <img src="./docs/figs/overview.png" alt="AIDR-SDK 架构" width="50%" />
</p>

- **Client**：以最小代码改动集成进 Agent 框架，监听每次工具调用，把上下文
  上报给 server，并执行 server 的决策。
- **Server**：接收 client 上报的信息，根据策略评估行为，生成决策并下发；
  同时提供管理、审计接口。

## 🗺️ 文档导航

- [`docs/claude-agent-sdk.md`](./docs/claude-agent-sdk.md) — Claude Agent SDK 适配器（新增）
- [`docs/agent-sdk-landscape.md`](./docs/agent-sdk-landscape.md) — Python / Node / Java / Go / Rust Agent 框架全景
- [`docs/cross-language-roadmap.md`](./docs/cross-language-roadmap.md) — 跨语言客户端策略
- [`docs/zh/`](./docs/zh) 与 [`docs/en/`](./docs/en) — 概念、DSL 参考、适配器指南（继承自上游，部分更新）

## 🎯 路线图

- 生产强化：持久化 provenance 图后端、分布式 rate-limit / approval 状态
- 跨语言客户端：TypeScript / Go 轻量 HTTP SDK（详见
  [跨语言路线](./docs/cross-language-roadmap.md)）
- 基于 mTLS / SPIFFE 的 principal 身份认证
- OpenTelemetry exporter 替换内置 telemetry
- 新规则上线前的 differential dry-run
- 按 sink 分类的 fail-open / fail-close 策略

## 🙏 上游致谢

AIDR-SDK 衍生自复旦大学系统软件与安全实验室开源的
[AgentGuard](https://github.com/WhitzardAgent/AgentGuard) 项目。DSL、策略引擎、
runtime、框架适配器等原始设计由 AgentGuard 团队贡献。上游 MIT 版权声明保留在
`LICENSE` 文件中。

## 📜 许可证

本项目使用 [MIT 许可证](./LICENSE)。
