# 求职 Agent (ClarifyAgent)

一个 **agentic 求职助手**：不是普通的前后端 CRUD，而是带 **agent harness** 的应用——工具调用循环、并行子 agent、全链路可观测性。帮你把简历、岗位、面试全流程跑通。

> Progressively learn and utilize agent.

## ✨ 功能模块

| 模块 | 说明 |
| --- | --- |
| ✍️ **简历改写** | 基于知识库最佳实践（XYZ 公式 / STAR / 量化 / 强动词）**有依据地**改写，附引用出处；**反幻觉校验**拦截编造的数字，缺数据用占位符提示补充 |
| 🎯 **建立匹配** | 简历 × JD 的确定性打分 + **并行子 agent**（JD 分析 / 简历分析 / 公司调研）综合报告 |
| 👋 **打招呼** | 多风格定制化开场消息 |
| 🎤 **模拟面试** | 多轮交互，面试官 agent 按 JD+简历出题、追问，支持中英文（外企） |
| 🔍 **面试复盘** | 面试记录分析（优劣势 / 遗漏点 / 参考答案 / 提升计划）+ web 搜索真实面经 |
| 🧠 **记忆 & 日报** | 长期记忆(洞见/原则/偏好/反复出现)自动沉淀与去重强化；一键生成**今日日报**并导出 Obsidian |

## 🏗️ 架构

```
┌────────────────────────── Frontend (React + Vite + TS + Tailwind) ─────────────────────────┐
│   五大模块 UI  ·  实时 Agent Trace 可视化（SSE 时间线）                                       │
└───────────────────────────────────────┬─────────────────────────────────────────────────────┘
                                         │ REST + SSE
┌───────────────────────────────────────┴─────────────────────────── Backend (FastAPI) ───────┐
│  Agent Harness   tool-calling loop · 并行 subagent (asyncio) · span/trace 可观测              │
│    ├─ LLM Gateway     OpenAI 兼容 + Anthropic 双协议 · 路由/fallback/重试 · tool-call 归一化   │
│    ├─ 内置工具         web_search(DuckDuckGo) · kb_list/kb_grep/kb_read (agentic search)       │
│    └─ 外部 MCP 工具    boss-agent-cli / linkedin-mcp（用户自配，可插拔）                        │
│  Domain (零依赖)  简历/JD 解析 · 技能库 · 匹配打分                                             │
│  Storage         SQLite（runs / traces / interview sessions）                                  │
└───────────────────────────────────────────────────────────────────────────────────────────┘
```

详见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 🔑 关键设计

- **双协议 LLM Gateway**：统一 `ChatProvider` 抽象，OpenAI 兼容（OpenAI/DeepSeek/通义/Moonshot/智谱）+ Anthropic 原生；tool-calling 内部归一化；跨 provider 自动 fallback。
- **Agentic search 取代向量 RAG**：简历最佳实践语料小而有界，用 `kb_grep`/`kb_read`（大模型 + grep）精确按 `文件:行号` 引用，无 embedding 依赖、无切块损失。
- **有依据 + 反幻觉的简历改写**：只重述既有事实 + 套用方法论，缺数据占位不编造，改写后做忠实度校验。
- **MCP 客户端**：招聘平台数据经用户自配的社区 MCP server 接入，合规与登录态交给上游。
- **可观测性**：每个 LLM/工具/子 agent = 一个 span，SSE 实时推前端做时间线，SQLite 落库可回看。
- **长期记忆（无向量库）**：`MemoryManager` 用 Jaccard 去重 + `salience` 强化，反复出现的要点自然浮升；`memory_search`/`memory_write` 为 agentic memory 工具；每次 run 后 `MemoryCurator` 自动反思沉淀洞见。
- **日报 + Obsidian**：`JournalWriter` 汇总当天 runs 与新增记忆生成日报；`ObsidianExporter` 直接写 vault 目录 markdown（零依赖），也可走 Obsidian MCP。
- **治理(HITL + 审计)**：副作用工具(如 MCP 打招呼/投递)按 `auto/confirm/deny` 策略门控,人工批准后放行,全程写审计日志;CORS 收紧可配置。
- **验证闭环 + LLM-as-judge**：简历改写「校验→自动修复→再校验」,把幻觉数字改成占位符;`/api/verify/judge` 对任意文本多维打分。
- **上下文管理**：`ContextManager` 在预算内压缩较旧/超长消息(保留 tool-call 配对),长对话与多轮工具调用更稳。
- **优雅降级**：未配置任何 LLM key 时，全部功能走确定性离线引擎，依然可用。

## 🚀 快速开始

### 后端

```bash
cd backend
pip install -e ".[all,dev]"        # 或最小安装：pip install -r requirements.txt
cp .env.example .env               # 按需填入 LLM key（不填也能离线运行）
uvicorn app.main:app --reload      # http://127.0.0.1:8000  (API 文档 /docs)
```

### 前端

```bash
cd frontend
npm install
npm run dev                        # http://127.0.0.1:5173（开发时代理 /api 到后端）
# 或生产构建后由后端直接托管：
npm run build                      # 产物 frontend/dist，被 FastAPI 挂到 /
```

## 🔌 配置多 provider / MCP

- **LLM**：在 `.env` 填入任意 provider 的 key（见 `backend/.env.example`）。用 `JOBSEEKER_PROVIDER_PRIORITY` 控制路由优先级与 fallback 顺序。
- **招聘平台（MCP）**：拷贝 `backend/mcp.example.json`，设 `JOBSEEKER_MCP_CONFIG` 指向它。求职者侧可用：
  - [`can4hou6joeng4/boss-agent-cli`](https://github.com/can4hou6joeng4/boss-agent-cli)（BOSS直聘/智联/51job，低风险合规）
  - [`stickerdaniel/linkedin-mcp-server`](https://github.com/stickerdaniel/linkedin-mcp-server)（LinkedIn / 外企）

  > 这些 server 用你**自己的登录态**在本地运行；本项目只作为 MCP 客户端消费其工具。使用前请阅读各项目的合规说明。

## 🧪 开发与质量

```bash
cd backend
pytest            # 28 项测试（domain / gateway / harness / grounding / modules / tools）
ruff check app tests
mypy app
```

CI（GitHub Actions）在每次推送运行 lint + type + test，见 `.github/workflows/ci.yml`。

## 📁 目录结构

```
backend/
  app/
    domain/      # 零依赖：解析、技能库、匹配
    gateway/     # 双协议 LLM 网关 + registry
    harness/     # agent loop / 并行 subagent / trace
    tools/       # web_search, kb_*, skill_match, memory_*
    mcp/         # MCP 客户端
    memory/      # 长期记忆(去重/强化/检索)
    governance/  # HITL 审批策略 + 审计
    modules/     # 功能模块 + 反幻觉校验 + 反思 + 日报 + LLM-as-judge
    export/      # Obsidian 导出
    storage/     # SQLite
    main.py      # FastAPI + SSE
  knowledge_base/resume/   # 可引用的简历最佳实践语料
  tests/
frontend/        # React + Vite + TS + Tailwind
docs/            # 架构文档
```

## 📄 License

MIT
