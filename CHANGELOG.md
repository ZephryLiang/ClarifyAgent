# Changelog

All notable changes to ClarifyAgent are documented in this file.

## [0.2.0] - 2026-07-07

### Added

- **Copilot** 对话入口：Chat + Artifact 双栏，对话式完成 JD 解读、调研、匹配
- `run_jd_analysis`：仅解读 JD，无需简历
- Proposal → Confirm 流程：完整匹配、改写、Gap、技术调研、学习计划
- **Gap 桥接**：`DeepGapAnalyzer` + `TechResearchAgent` + `ProjectAdvisor`
- **多 JD 共性**：`RequirementSynthesizer` + `LearningPlanGenerator`（P0–P3 + 有限时间）
- **岗位评估**：`RoleAssessor` + `JobMarketAggregator`
- **双轨记录 (H1/H2)**：`activity_events` 用户流水 + `system_releases` 系统发版记录
- 日报 / **周报**：`JournalWriter(period=week)`
- API: `/api/chat/*`, `/api/meta/changelog`, `/api/activity`
- Memory kind: `heuristic`

### Changed

- 默认 Tab 改为 Copilot
- `JournalWriter` 汇总 Copilot activity 事件

## [0.1.0] - Baseline

- Tab 模块：简历改写、匹配、打招呼、模拟面试、复盘
- Agent Harness、双协议 Gateway、MCP、记忆日报
