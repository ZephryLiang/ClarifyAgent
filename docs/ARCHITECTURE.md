# 架构设计文档

本文件说明 求职 Agent 的架构、关键设计决策与遵循的软件工程原则。

## 1. 分层与依赖方向

```
api (FastAPI, main.py)
        │  依赖
        ▼
service (AppServices 门面)
        │
        ▼
modules (5 大功能)  ──►  harness (agent/subagent/trace/tools)
        │                        │
        ▼                        ▼
domain (纯逻辑，零依赖)     gateway (LLM 抽象 + 适配器)
                                 ▲
                                 │ 实现
                    openai / anthropic 适配器
```

依赖只能自上而下。**`domain` 层不依赖任何上层，也不依赖第三方库**，因此可脱离 Web/LLM 独立测试与复用。

## 2. 关键设计决策（ADR 摘要）

### 2.1 双协议 LLM Gateway（OpenAI 兼容 + Anthropic 原生）
- **动机**：用户要求同时支持 OpenAI 兼容协议与 Anthropic 协议，且要多 provider。
- **决策**：定义统一 `ChatProvider` 抽象与中间数据模型（`Message`/`ToolCall`/`ChatResponse`）。`OpenAIAdapter` 与 `AnthropicAdapter` 各自把中间模型翻译成厂商格式，并把响应翻译回来。
- **难点**：tool-calling 归一化。OpenAI 用 `tools`/`tool_calls`+`role:tool`；Anthropic 用 `tool_use` content block + 在 *user* 消息里回传 `tool_result`，且 `system` 是顶层参数。适配器内部完成双向翻译，上层 harness 完全不感知。
- **备选**：LiteLLM。为了把 token/耗时/重试/fallback 完全接入自建 trace，选择自建轻量网关。

### 2.2 Agentic search 取代向量 RAG
- **动机**：简历最佳实践语料小而有界（几十篇），且要求「有依据、可溯源」。
- **决策**：不建向量库，改为**文件语料 + `kb_list`/`kb_grep`/`kb_read` 工具**，让 agent 自己检索、读全文、按 `文件:行号` 引用（即「大模型 + grep」/ agentic search）。
- **收益**：无 embedding 基建；无切块信息损失；引用可验证；语料扩展 = 丢一个文件。

### 2.3 有依据 + 反幻觉的简历改写
- **原则**（`knowledge_base/resume/anti_hallucination.md` 为硬约束）：不新增事实、不夸大角色、不编造数字；缺数据用 `[待补充: ...]` 占位。
- **流程**：agentic 检索 KB → 套用方法论改写 → **忠实度校验**（`grounding.py`：抽取改写中的数字，凡不在原文且非占位符者判为幻觉并标红）。
- **降级**：无 LLM 时用确定性启发式（弱动词/缺量化检测）生成带引用的建议。

### 2.4 MCP 客户端集成招聘平台
- **动机**：不自建爬虫（反爬 + 合规风险）。
- **决策**：harness 作为 **MCP 客户端**，消费用户本地运行的社区 MCP server（boss-agent-cli、linkedin-mcp 等），远程工具经 `MCPTool` 以 `server__tool` 命名空间并入统一 `ToolRegistry`。
- **降级**：未装 `mcp` SDK 或未配置时，零 MCP 工具、正常运行。

### 2.5 可观测性优先
- 每个 LLM 调用 / 工具 / 子 agent = 一个 `Span`（含 trace_id、parent_id、耗时、token、provider、状态）。
- `Tracer` 既缓存 span，又通过 `asyncio.Queue` 暴露事件流；API 层用 SSE 实时转发到前端时间线；`Store` 落库 SQLite 供回看。

## 3. 软件工程原则与落点

| 原则 | 落点 |
| --- | --- |
| 分层 / 关注点分离 | `domain` / `gateway` / `harness` / `tools` / `modules` / `storage` / `api` |
| 依赖倒置（面向接口）| `ChatProvider`、`Tool` 抽象；harness 依赖抽象而非具体 SDK |
| 开闭原则 | 加 provider=加适配器+配置；加工具=实现接口+注册；加依据=加文件 |
| 单一职责 | 每个模块聚焦单一职责，函数短小 |
| 依赖注入 / 可测试 | Gateway/Agent/Service 均可注入依赖；`FakeProvider` 驱动确定性测试 |
| 类型与契约 | 全量 type hints + `dataclass`；API 边界 pydantic；mypy 通过 |
| 错误处理 / 降级 | provider 异常归一为 `ProviderError`；全链路离线降级；未知工具不抛异常 |
| 配置管理（12-factor）| 全 env 驱动；密钥不入代码、不进日志 |
| 安全合规 | KB 路径限定防遍历；招聘数据走用户自有登录态的 MCP；默认低风险操作 |
| 质量门禁 | ruff + mypy + pytest，CI 三道门 |

## 4. 请求时序（以「建立匹配」为例）

```
Client ──POST /api/match (stream)──► FastAPI
  FastAPI 创建 Tracer，后台跑 Matcher.run，同时 SSE 转发 tracer 事件
    Matcher: domain.compute_match（确定性分数）
    Orchestrator.run_parallel:
        subagent: jd-analysis      ─┐
        subagent: resume-analysis   ├─ asyncio.gather 并行
        subagent: company-research ─┘ (web_search 工具)
    synthesis agent 汇总
  完成 → 存 Store → SSE 推送 result 事件（含 trace 摘要）
Client 前端：实时渲染 span 时间线 + 最终报告
```

## 5. 可扩展点

- **新 provider**：在 `config.py` 加一条 `ProviderConfig`（或走 env 覆盖 base_url/model）。
- **新工具**：实现 `Tool` 并在 `tools/__init__.py` 注册；或通过 MCP 引入。
- **新知识依据**：往 `knowledge_base/` 丢 `.md`，agentic search 自动可检索。
- **新功能模块**：在 `modules/` 组合 harness 能力，接一个 `main.py` 路由即可。
