# ClarifyAgent 产品说明

ClarifyAgent 是面向主动求职者的 **Chat-first Copilot**，覆盖 JD 解读 → 匹配 → Gap 桥接 → 技术调研 → 简历优化 → 打招呼 → 模拟面试 → 复盘 → 市场洞察 → 记忆沉淀。

## 核心交互原则

1. **对话主线**：用户粘贴 JD/简历后，Agent 先保存 workspace，再**询问**意图（解读 / 调研 / 匹配），不擅自跑重流程。
2. **Proposal → Confirm → Run**：完整匹配、改写、Gap、技术调研、学习计划、模拟面试、复盘等重操作需用户确认。
3. **Artifact 面板**：结构化结果（匹配报告、Gap、学习计划等）在右侧展示，可切换历史 artifact。
4. **双轨记录**：
   - **H1** `activity_events`：用户行为流水（capture_jd、match、gap…）
   - **H2** `system_releases` / `system_change_events`：产品版本与系统变更

## 主要流程

### A. 基础 Copilot
粘贴 JD → `update_workspace` → 询问 → 可选：`run_jd_analysis` / `research_company` / `quick_match` / `propose_match_analysis`

### B. 公司调研
用户确认后 `research_company`，结果写入 artifact + activity。

### C. 面试循环
`propose_mock_interview` → confirm → `run_mock_interview`；结束后粘贴 transcript → `propose_retrospective` → confirm → `run_retrospective`

### E. Gap 桥接（流程 E 剧本）

1. 粘贴 JD + 简历 → `quick_match` 得低分
2. Copilot 建议 `propose_deep_gap_analysis` → 用户确认 → `run_deep_gap_analysis`
3. 输出 `GapAnalysis` + `reframe_candidates`（改写角度）与 `new_project` 路径
4. 用户选新项目 → `propose_tech_research` → 确认 → 多源调研 + `SourceScorer` 评分
5. `ProjectAdvisor` 产出带引用的 `ProjectProposal`；`ResearchCurator` 沉淀 heuristic 记忆
6. 附带 `RoleAssessment`；多岗位时更新 `JobMarketReport`

评分 rubric 见 `knowledge_base/research/scoring_rubric.md`；岗位 taxonomy 见 `knowledge_base/roles/taxonomy.md`。

### F/G. 多 JD 与学习计划
多份 JD 存入 `workspace.jobs` → `run_requirement_synthesis` → `propose_learning_plan` → 用户用自然语言 `revise_learning_plan`（无 P0/P2 按钮）

### H. 日报 / 周报
`generate_journal(period=day|week)` 或 Memory Tab；汇总 H1 activity + 记忆摘要

## 评分与 Rubric

- 技术调研素材评分：见 `knowledge_base/research/scoring_rubric.md`
- 学习计划优先级：见 `knowledge_base/learning/priority_rubric.md`
- 岗位类型：见 `knowledge_base/roles/taxonomy.md`

## API 入口

| 路径 | 用途 |
|------|------|
| `POST /api/chat/sessions` | 创建会话（可 seed workspace） |
| `POST /api/chat/sessions/{id}/message` | SSE 对话 |
| `POST /api/chat/sessions/{id}/confirm` | 确认 proposal |
| `GET /api/meta/version` | 版本与 what's new |
| `GET /api/activity` | H1 用户流水 |

Legacy Tab（简历改写、匹配等）保留为高级入口，与 Copilot workspace 同步。
