# Agent SDK 生态全景与 AIDR-SDK 覆盖矩阵

> 调研日期：2026-06-03
>
> 本文档梳理截至 2026 年中主流 LLM Agent SDK / 框架的实现语言、多语言版本
> 情况，以及 AIDR-SDK 当前的覆盖情况。用作内部选型与 adapter roadmap 的
> 参考底座。

## 1. 一句话定位

AIDR-SDK 当前是 **Python first** 的项目。Python 生态的主流 Agent 框架基本
都有内置 adapter；非 Python 生态（Node / Java / Go / Rust）需要走"跨语言
路线"——见 [cross-language-roadmap.md](./cross-language-roadmap.md)。

## 2. 主流框架矩阵

### 2.1 Python 生态（主流，市场占比 ~70%+）

| 框架 | 实现语言 | 多语言版本 | AIDR-SDK 内置支持 | 备注 |
|------|---------|-----------|------------------|------|
| **LangChain / LangGraph** | Python | LangChain.js（TS）、LangChain4j（Java）、LangChainGo（Go） | ✅ `attach_langchain` | 跨语言生态最广 |
| **AutoGen** | Python | AutoGen .NET（C#） | ✅ `attach_autogen` | Microsoft；0.2 / 0.3 / 0.4 三套 API 都兼容 |
| **OpenAI Agents SDK** | Python | OpenAI Agents JS（TS）官方 | ✅ `attach_openai_agents` | 2025 推出，双语言官方 |
| **Claude Agent SDK** | Python + TypeScript | 官方 Python + 官方 TS（无其他语言） | ✅ `attach_claude_agent` *(本 fork 新增)* | 2025 中由 "Claude Code SDK" 改名 |
| **CrewAI** | Python | 无 | ⚠️ 需自定义 adapter | 多 agent 协作 |
| **LlamaIndex Agents** | Python | LlamaIndex.TS（TS） | ⚠️ 需自定义 adapter | 偏 RAG |
| **Dify** | Python（后端） + TS（前端） | 无 | ✅ `attach_dify` | 流式事件框架，无 pre-execution hook，只能事后取消 |
| **Pydantic AI** | Python | 无 | ⚠️ 需自定义 adapter | 强类型，2024 新起 |
| **Smolagents** | Python | 无 | ⚠️ 需自定义 adapter | HuggingFace 出品，轻量 |
| **Agno**（旧名 phidata） | Python | 无 | ⚠️ 需自定义 adapter | 简洁 |
| **AutoGPT** | Python | 无 | ❌ | 自主 agent 鼻祖 |
| **Haystack Agents** | Python | 无 | ❌ | deepset；偏 RAG |

### 2.2 TypeScript / Node 生态（第二集团）

| 框架 | 实现语言 | 多语言版本 | AIDR-SDK 内置支持 | 备注 |
|------|---------|-----------|------------------|------|
| **Vercel AI SDK** | TypeScript | 无 | ❌ | Web 前端为主，含 agent 抽象 |
| **LangChain.js** | TypeScript | 同上游 | ⚠️ 走跨语言 HTTP | LangChain 的 TS 移植 |
| **OpenAI Agents JS** | TypeScript | 同上游 | ⚠️ 走跨语言 HTTP | 官方 |
| **Claude Agent SDK TS** | TypeScript | 同上游 | ⚠️ 走跨语言 HTTP | 官方 |
| **Mastra** | TypeScript | 无 | ❌ | 2024 新起，TS 原生 agent 框架 |
| **Inngest AgentKit** | TypeScript | 无 | ❌ | TS workflow + agent |
| **Claude Code CLI** | TypeScript / Node | 通过 hooks 配置集成 | ⚠️ 通过 `PreToolUse` hook + HTTP server 间接接 | 不是 SDK，是 CLI |

### 2.3 Java / .NET 生态（企业市场）

| 框架 | 实现语言 | 多语言版本 | AIDR-SDK 内置支持 | 备注 |
|------|---------|-----------|------------------|------|
| **Spring AI** | Java | 无 | ❌ | Spring 生态首选 |
| **LangChain4j** | Java | LangChain 思想的独立 Java 实现 | ❌ | 与 LangChain 兼容但独立 |
| **Semantic Kernel** | C# 主 | Python、Java 官方支持 | ❌ | Microsoft；多语言一等公民 |
| **AutoGen .NET** | C# | 同上游 | ❌ | Microsoft |

### 2.4 Go 生态

| 框架 | 实现语言 | 多语言版本 | AIDR-SDK 内置支持 | 备注 |
|------|---------|-----------|------------------|------|
| **Eino** | Go | 无 | ❌ | CloudWeGo / 字节跳动 |
| **LangChainGo** | Go | 无 | ❌ | LangChain 的 Go 社区移植 |

### 2.5 Rust 生态（新兴）

| 框架 | 实现语言 | 多语言版本 | AIDR-SDK 内置支持 | 备注 |
|------|---------|-----------|------------------|------|
| **Rig** | Rust | 无 | ❌ | 0xPlaygrounds；2024 起，社区活跃 |
| **Swiftide** | Rust | 无 | ❌ | RAG + agent |
| **llm-chain** | Rust | 无 | ❌ | 早期 Rust LLM 生态 |

## 3. 当前 AIDR-SDK 内置 adapter 详情

`agentguard/sdk/adapters/` 下的实现：

| Adapter | 代码行数 | 拦截机制 | 拦截能力 | 已知坑 |
|---------|---------|---------|---------|------|
| `langchain.py` | 112 | patch `BaseTool.func` / `coroutine`；兼容 langgraph CompiledGraph / 未编译 builder | 完整 pre + post | langgraph 编译态/未编译态两条路径 |
| `autogen.py` | 244 | patch `_tools` list / `function_map` dict；三层 fallback | 完整 | 0.4 把 callable 改名 `_func` 曾导致历史失效 |
| `openai_agents.py` | 250 | patch `FunctionTool.on_invoke_tool` + JSON↔dict 协议转换 | 完整 | async 序列化坑：原 callable 可能 async，wrapper 必须 async |
| `dify.py` | 212 | patch 流式生成器 + `stop_message` 取消 | **只观察 + 整段终止**，无 pre-execution 拦截 | 不能 DENY 单次调用，不能 DEGRADE 改参 |
| `openclaw.py` | 20 | `runtime.tool_registry` dict 项替换 | 完整 | 极简；目标框架必须有 `tool_registry: dict` 属性 |
| `claude_agent.py` | ~340 *(新增)* | 两层：(1) 包装 SDK MCP server 内的 `@tool` 函数；(2) 注入 `PreToolUse` hook 拦截 Claude Code 内置工具 | 完整 | HUMAN_CHECK / LLM_CHECK 在 hook 路径里只能映射为 `ask`，不能真正等待 |

## 4. 接入 difficulty 三类划分

把可接入性按 M1 章节里的分类整理：

### A 类：tool 是可枚举的可调用对象

最简单。找到注册表 / 列表 / 字典，把每个值替换成 `wrap_tool(original)`。

- LangChain（A 类）
- AutoGen ≤ 0.3（A 类）
- OpenClaw（A 类）
- Claude Agent SDK 的 SDK MCP server tools（**A 类**）
- CrewAI（推测 A 类，未验证）
- LlamaIndex Agents（推测 A 类，未验证）

**典型 adapter 代码量：20-150 行**

### B 类：tool 是对象，可调用部分藏在属性下

要 probe 多种属性名，处理 frozen dataclass 的 setattr 失败。

- AutoGen ≥ 0.4（B 类，`_func` 私有属性）
- OpenAI Agents（B 类，需要 JSON↔dict 协议转换）
- LangChain BaseTool 也算（func / coroutine / invoke 三个）

**典型 adapter 代码量：200-300 行**

### C 类：tool 调用没有可拦截"前后"，只有事件流

最棘手。SDK 拿到事件时，工具已在远端执行完。

- Dify（C 类，只能事后 `stop_message`）
- Claude Code CLI 的内置工具（**C 类**，必须靠 `PreToolUse` hook + 不能挂起等审批）

**典型 adapter 代码量：200+ 行 + 能力降级**

## 5. 跨步链路（TRACE）能力可移植性

各框架对 AIDR-SDK 核心创新（TRACE 跨步链路检测）的支持度：

| 框架 | 能否做完整 TRACE | 限制 |
|------|---------------|------|
| LangChain | ✅ | 同步 + 异步都可 |
| AutoGen | ✅ | 同步 + 异步都可 |
| OpenAI Agents | ✅ | 异步（需 await） |
| Claude Agent SDK + SDK MCP tools | ✅ | 异步 |
| Claude Agent SDK + Built-in tools | ⚠️ | hook 路径，可观察可拦截但 HUMAN_CHECK 不能挂起 |
| Dify | ❌ | 没有同步 session_id 维持 |
| TypeScript / Go / Rust（远端 HTTP） | ✅ | 需要客户端正确传 session_id |

## 6. 选型建议

### 短期（0-3 个月）

1. **Python 重投资**：完整 SDK + 6 个 adapter（含本次新增 Claude Agent SDK）已经覆盖 Python 主流 80%+ 的需求
2. **新增 CrewAI / Pydantic AI adapter**：业务有需求时 1-2 周可完成

### 中期（3-6 个月）

3. **TypeScript 轻量 HTTP 客户端**：覆盖 Vercel AI SDK / Mastra / LangChain.js / Claude Agent SDK TS / OpenAI Agents JS。预计 2-3 周完整版（含 contextvars 等价物 `AsyncLocalStorage`）
4. **Claude Code CLI 集成 cookbook**：用 hooks + curl + 一个 sidecar Python 进程实现完整能力闭环

### 长期（6 个月+）

5. **Java / Go 客户端**：等企业客户出现真实需求再投入
6. **WebAssembly DSL evaluator**：把 policy/evaluator 编进 wasm，实现离线评估，所有语言通用 —— 投入很大，仅在多语言需求集中时考虑

## 7. 参考链接

- LangChain: https://github.com/langchain-ai/langchain
- AutoGen: https://github.com/microsoft/autogen
- OpenAI Agents SDK: https://github.com/openai/openai-agents-python
- Claude Agent SDK (Python): https://github.com/anthropics/claude-agent-sdk-python
- Claude Agent SDK (TS): https://github.com/anthropics/claude-agent-sdk-typescript
- Claude Code docs: https://docs.claude.com/en/docs/claude-code
- CrewAI: https://github.com/crewAIInc/crewAI
- LlamaIndex: https://github.com/run-llama/llama_index
- Pydantic AI: https://github.com/pydantic/pydantic-ai
- Smolagents: https://github.com/huggingface/smolagents
- Agno: https://github.com/agno-agi/agno
- Vercel AI SDK: https://github.com/vercel/ai
- Mastra: https://github.com/mastra-ai/mastra
- Semantic Kernel: https://github.com/microsoft/semantic-kernel
- Spring AI: https://github.com/spring-projects/spring-ai
- LangChain4j: https://github.com/langchain4j/langchain4j
- Eino: https://github.com/cloudwego/eino
- LangChainGo: https://github.com/tmc/langchaingo
- Rig: https://github.com/0xPlaygrounds/rig
