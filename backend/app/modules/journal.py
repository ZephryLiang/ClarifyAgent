"""Daily report (今日日报) generator.

Aggregates the day's runs and newly-captured memories into a Markdown report:
what was done, key highlights, insights learned, recurring themes, and next
actions. With an LLM it produces a polished narrative; offline it builds a solid
structured report deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from ..memory import MemoryManager
from ..storage import Store
from .base import llm_available

_MODULE_LABELS = {
    "resume_rewrite": "简历改写",
    "matching": "岗位匹配",
    "outreach": "打招呼",
    "interview": "模拟面试",
    "retrospective": "面试复盘",
    "journal": "日报",
}

_SYSTEM = """你是求职教练，为求职者写一份简洁、鼓励且可执行的今日日报（Markdown）。
基于给定的当日活动数据与洞见，输出：概览、亮点、今日学到的洞见、反复出现的主题、明日行动清单。
不要编造未提供的数据。"""


@dataclass
class JournalResult:
    date: str = ""
    markdown: str = ""
    stats: dict[str, int] = field(default_factory=dict)
    highlights: list[str] = field(default_factory=list)
    llm_used: bool = False

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "markdown": self.markdown,
            "stats": self.stats,
            "highlights": self.highlights,
            "llm_used": self.llm_used,
        }


class JournalWriter:
    def __init__(self, store: Store, memory: MemoryManager, gateway: Gateway | None = None) -> None:
        self.store = store
        self.memory = memory
        self.gateway = gateway

    @staticmethod
    def _today_start() -> float:
        now = datetime.now()
        return datetime(now.year, now.month, now.day).timestamp()

    def _collect(self) -> dict[str, Any]:
        start = self._today_start()
        runs = [r for r in self.store.runs_since(start) if r["module"] != "journal"]
        stats: dict[str, int] = {}
        highlights: list[str] = []
        for r in runs:
            stats[r["module"]] = stats.get(r["module"], 0) + 1
            res = r.get("result") or {}
            if r["module"] == "matching" and res.get("match"):
                m = res["match"]
                highlights.append(f"匹配「{(r['input'] or {}).get('job_text','')[:16]}…」得分 {m.get('score')}")
            elif r["module"] == "resume_rewrite":
                highlights.append(f"改写 {len(res.get('suggestions', []))} 条简历经历")
            elif r["module"] == "retrospective" and res.get("strengths"):
                highlights.append("完成一次面试复盘")
        new_memories = [m for m in self.memory.list() if m.created_at >= start]
        recurring = [m for m in self.memory.list() if m.salience >= 2][:8]
        return {"runs": runs, "stats": stats, "highlights": highlights[:8],
                "new_memories": new_memories, "recurring": recurring}

    async def run(self, tracer: Tracer | None = None) -> JournalResult:
        tracer = tracer or Tracer()
        span = tracer.start_span("journal", SpanKind.AGENT, has_llm=llm_available(self.gateway))
        try:
            date = datetime.now().strftime("%Y-%m-%d")
            data = self._collect()
            stats = data["stats"]

            if llm_available(self.gateway):
                markdown = await self._narrative(date, data, tracer, span.id)
                used = True
            else:
                markdown = self._template(date, data)
                used = False

            result = JournalResult(date=date, markdown=markdown, stats=stats,
                                   highlights=data["highlights"], llm_used=used)
            tracer.end_span(span, SpanStatus.OK, runs=len(data["runs"]))
            return result
        except Exception as exc:  # noqa: BLE001
            tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
            raise

    async def _narrative(self, date: str, data: dict[str, Any], tracer: Tracer, parent_id: str) -> str:
        assert self.gateway is not None
        agent = Agent(self.gateway, ToolRegistry(), tracer, system=_SYSTEM,
                      name="journal-writer", temperature=0.5, parent_span_id=parent_id)
        payload = {
            "date": date,
            "stats": {_MODULE_LABELS.get(k, k): v for k, v in data["stats"].items()},
            "highlights": data["highlights"],
            "new_insights": [m.content for m in data["new_memories"]],
            "recurring": [f"{m.content} (x{m.salience})" for m in data["recurring"]],
        }
        import json

        out = await agent.run("当日数据:\n" + json.dumps(payload, ensure_ascii=False, indent=2))
        return out.output.strip() or self._template(date, data)

    def _template(self, date: str, data: dict[str, Any]) -> str:
        lines = [f"# 今日求职日报 · {date}", "", "## 概览"]
        if data["stats"]:
            for mod, n in data["stats"].items():
                lines.append(f"- {_MODULE_LABELS.get(mod, mod)}: {n} 次")
        else:
            lines.append("- 今日暂无活动记录。")

        if data["highlights"]:
            lines += ["", "## 亮点"]
            lines += [f"- {h}" for h in data["highlights"]]

        if data["new_memories"]:
            lines += ["", "## 今日学到的洞见"]
            lines += [f"- [{m.kind}] {m.content}" for m in data["new_memories"]]

        if data["recurring"]:
            lines += ["", "## 反复出现的主题（值得重点处理）"]
            lines += [f"- {m.content} (出现 {m.salience} 次)" for m in data["recurring"]]

        lines += ["", "## 明日行动"]
        gaps = [m for m in data["recurring"] if "skill-gap" in m.tags]
        if gaps:
            lines += [f"- 补齐反复缺失的技能: {m.content}" for m in gaps[:3]]
        lines += [
            "- 针对高匹配岗位主动打招呼，抢占先机。",
            "- 用 STAR/量化 打磨 1-2 条简历经历。",
        ]
        return "\n".join(lines)
