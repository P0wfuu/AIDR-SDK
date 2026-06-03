# AIDR-SDK 跨语言治理路线图

> 目标：让 AIDR-SDK **不限于 Python**，能治理 TypeScript / Java / Go / Rust 等
> 实现的 Agent 系统。

## 1. 核心观察

AIDR-SDK 当前架构本身就是 **控制面 / 数据面分离**：

- **控制面（server）**：HTTP API，跑在一台机器上，做策略评估、provenance
  追踪、HUMAN_CHECK / LLM_CHECK 调度。
- **数据面（SDK）**：跑在每个 Agent 进程里，拦截工具调用，把上下文上报给
  server，并执行 server 的决策。

控制面**只需要写一次**。数据面**每个语言写一份**就够了。

```
       ┌────────────────────────────────────────────────────────┐
       │   AIDR-SDK Control Server (Python, ONE instance)       │
       │   - DSL parser / evaluator                              │
       │   - Provenance graph                                   │
       │   - Audit / Review queue                                │
       │   - Web UI                                              │
       │   POST /v1/evaluate (RuntimeEvent → Decision)           │
       └──────────────────────────────────────────────────────────┘
              ▲              ▲              ▲              ▲
              │ HTTP         │ HTTP         │ HTTP         │ HTTP
              │              │              │              │
       ┌──────┴────┐  ┌──────┴────┐  ┌──────┴────┐  ┌─────┴─────┐
       │  Python   │  │  TS/Node  │  │   Go      │  │   Java    │
       │  SDK ✅    │  │  client   │  │   client  │  │   client  │
       │           │  │  (todo)   │  │   (todo)  │  │   (todo)  │
       └───────────┘  └───────────┘  └───────────┘  └───────────┘
```

## 2. 实现路径选项

### 路径 A：HTTP-only thin client（推荐起点）

每个语言写一个 100-300 行的轻量客户端，序列化 `RuntimeEvent` JSON 喂
`/v1/evaluate`，按 `Decision` 拦截 / 改写 / 放行。

**工作量**：每语言 1-2 周。
**适用**：任何能发 HTTP 的语言。
**参考实现**：Python `agentguard/sdk/client.py:RemoteGuardClient`（195 行 stdlib
实现，无 `requests` 依赖）。

**典型客户端职责**：
1. 维持 session 上下文（principal / session_id / goal / scope）
2. 工具包装：把 framework-native tool 包成"调用前 POST /v1/evaluate"的版本
3. 决策应用：DENY → raise；DEGRADE/REDACT → rewrite args；HUMAN_CHECK → 阻塞等回调
4. fail_open 配置：HTTP 失败时是放行还是阻断
5. 后处置：结果回报（POST /v1/events for completed / failed）

### 路径 B：完整 SDK（含 contextvars 等价物）

仿照 Python SDK 完整移植，含 session 管理、wrap_tool 等价物、adapter 体系。

**工作量**：每语言 1-2 月。
**适用**：优先 TS/Node、Java、Go。
**何时启动**：当某个语言的内部使用量超过 100 个 agent 时。

### 路径 C：WebAssembly DSL evaluator

把 `policy/evaluator` 编进 wasm，所有语言离线评估，不需要 server。

**工作量**：4-6 月。
**适用**：长期方案；边缘场景 / 低延迟场景。
**何时启动**：当多语言需求集中、且 server 调用延迟成为瓶颈时。

## 3. 优先级建议（按 ROI）

| 顺序 | 语言 | 路径 | 触发条件 | ETA |
|------|------|------|---------|-----|
| 1 | **TypeScript / Node** | A | Vercel AI SDK / Claude Agent SDK TS / OpenAI Agents JS 客户增加 | 2-3 周 |
| 2 | **Go** | A | 内部基础设施 / 字节系 Eino 用户出现 | 2-3 周 |
| 3 | **TypeScript / Node** | B | 用 A 已不满足（需要复杂 session 模型） | 1-2 月 |
| 4 | **Java** | A → B | 金融 / 银行客户的 Spring AI / LangChain4j 接入 | 1-2 月 |
| 5 | **Rust** | A | 极少数 Rig 用户；边缘场景 | 按需 |
| 6 | 全部 | C wasm | 多语言需求成熟后 | 6+ 月 |

## 4. TypeScript thin client 设计草案

如果先做 TS（推荐）：

```typescript
// aidr-sdk/ts/src/client.ts (~200 行预期)

export interface Principal {
  agent_id: string;
  session_id: string;
  role?: string;
  trust_level?: number;
}

export interface Decision {
  action: 'allow' | 'deny' | 'human_check';
  reason?: string;
  obligations?: Obligation[];
  matched_rules?: string[];
}

export class GuardClient {
  constructor(opts: {
    remoteUrl: string;
    apiKey?: string;
    failOpen?: boolean;
    timeoutMs?: number;
  }) { ... }

  // session 上下文用 AsyncLocalStorage（Node 的 contextvars 等价物）
  start(principal: Principal, goal?: string): void { ... }
  
  // 包装一个 tool 函数：在调用前 POST /v1/evaluate
  wrapTool<F extends (...args: any) => any>(
    name: string,
    fn: F,
    labels?: ToolStaticLabel,
  ): F { ... }

  // POST /v1/evaluate
  async evaluate(event: RuntimeEvent): Promise<Decision> { ... }

  // 框架适配器
  attachVercelAiSdk(toolset: any): void { ... }
  attachClaudeAgentSdkTs(options: any): void { ... }
  attachLangChainJs(executor: any): void { ... }
}
```

**关键依赖**：
- `node:async_hooks` 的 `AsyncLocalStorage` —— Python `contextvars` 等价物
- 标准 `fetch`（Node 18+ 自带）—— 不引入 axios

**适配器优先级**：
1. Vercel AI SDK（最热门）
2. Claude Agent SDK TS
3. OpenAI Agents JS
4. LangChain.js
5. Mastra

## 5. 协议契约（不依赖语言）

控制面 API 是所有语言客户端的契约。需要冻结并文档化：

| Endpoint | 用途 | Schema 状态 |
|----------|------|------------|
| `POST /v1/evaluate` | 单次决策 | ✅ 已存在 |
| `POST /v1/evaluate/batch` | 批量决策 | ✅ 已存在 |
| `POST /v1/events` | 完成 / 失败事件上报 | ⚠️ 需明确 |
| `GET /v1/health` | 健康检查 | ✅ |
| `POST /v1/tools` | 工具目录上报 | ✅ |
| `GET /v1/approvals/pending` | 拉取待审工单 | ✅ |
| `POST /v1/approvals/{id}/{approve,deny}` | 工单回执 | ✅ |

**TODO**：为协议契约写一份 `docs/api-contract.md`（含 JSON schema），让跨语言
客户端有统一依据。

## 6. session_id 传播在不同语言里的等价物

| 语言 | 机制 | 复杂度 |
|------|------|------|
| Python | `contextvars.ContextVar` | ✅ 已实现 |
| TypeScript / Node | `AsyncLocalStorage` (node:async_hooks) | 低 |
| Java | `InheritableThreadLocal` + Loom virtual threads | 中 |
| Go | `context.Context` 手动传递（无隐式） | 中（要求 API 改造） |
| Rust | `tokio::task_local!` 或显式 context 参数 | 中 |

**Go 是最麻烦的** —— 没有隐式 context propagation，每个 tool 函数签名都得改成
`func(ctx context.Context, args ...) error`。这意味着 Go 客户端不能完全做到
"零侵入接入"。

## 7. 不需要客户端的场景：Sidecar 模式

对于无法/不愿写 SDK 的小众语言（Ruby、PHP、Elixir、Erlang...）：

```
   Agent process (任意语言)
        │
        │ subprocess / unix socket / stdin-stdout
        ▼
   aidr-sidecar (Python; 包装 GuardClient)
        │
        │ HTTP
        ▼
   Control Server
```

Sidecar 接 stdin（JSON Lines）/ Unix socket，转发给 Python SDK，回 stdout。
**Agent 只需要把 tool_call payload 序列化成 JSON 写过去**。

这是覆盖小语言的"最后手段"，工程上简单但延迟略高（IPC + 序列化）。

## 8. 行动建议（用户决策）

如果目标是"近期生产可用 + 覆盖主要 Agent 框架"：

1. **保持 Python SDK 为主**（已经包含 6 个 adapter，含 Claude Agent SDK）
2. **优先做 TypeScript thin client（路径 A）**，2-3 周
3. **冻结 HTTP API 契约**，写 `docs/api-contract.md`
4. **Go / Java 按业务需求驱动**，不预先投入

如果目标是"建立跨语言治理平台"：

5. **完整 TS SDK（路径 B）**，3-4 月
6. **wasm evaluator（路径 C）研究**，并行 6 月

## 9. 参考

- 控制面参考实现：`agentguard/sdk/client.py`（Python `RemoteGuardClient`）
- 协议数据模型：`agentguard/models/events.py`（Pydantic schema）
- 现有 Adapter 模板：`agentguard/sdk/adapters/base.py`
