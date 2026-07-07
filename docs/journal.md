# Journal: 日报与周报

## 数据来源

| 轨道 | 表 | 内容 |
|------|-----|------|
| H1 用户活动 | `activity_events` | capture_jd, match, gap, tech_research, journal… |
| 长期记忆 | `memories` | insight, principle, heuristic… |
| H2 系统变更 | `system_releases`, `system_change_events` | 发版、API 变更（**不**写入用户日报正文） |

## period 参数

- `day`：当日 00:00 至今的 activity + 记忆增量
- `week`：近 7 日 activity 汇总 + 周度统计

## 生成方式

1. **Copilot**：`generate_journal` 工具或 chip「生成本周周报」
2. **Memory Tab**：「生成今日日报」/「本周周报」按钮
3. **API**：`POST /api/journal` body `{ "period": "day" | "week" }`

## 导出

`POST /api/journal/export` 写入 Obsidian vault（若已配置路径）。

## 与 Copilot 的关系

Copilot 每次 tool 调用通过 `ActivityLedger.record()` 写入 H1；日报/周报是这些事件的**可读摘要**，帮助用户回顾求职进展，而非替代 artifact 详情。
