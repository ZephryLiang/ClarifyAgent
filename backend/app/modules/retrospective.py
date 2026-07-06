"""Module ⑤: interview retrospective / review (面试复盘).

Takes an interview transcript and produces structured feedback: strengths,
weaknesses, missed points, model answers, and an improvement plan. When an LLM
is available it can use web search to pull real interview experiences ("面经")
for the target company/role to sharpen the feedback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from .base import extract_json, llm_available

_SYSTEM = """你是资深面试教练，负责面试复盘。请客观、具体、可执行。
可以用 web_search 查找目标公司/岗位的真实面经作为参考（若不可用则跳过）。
只输出 JSON：
{
  "overall": "总体评价（含大致通过概率区间，说明依据）",
  "strengths": ["..."],
  "weaknesses": ["..."],
  "missed_points": ["回答中本可以提到但遗漏的关键点"],
  "model_answers": [{"question": "...", "suggestion": "更好的回答思路"}],
  "improvement_plan": ["可执行的提升建议"],
  "references": ["引用的面经/资料链接（如有）"]
}"""


@dataclass
class RetrospectiveResult:
    overall: str = ""
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    missed_points: List[str] = field(default_factory=list)
    model_answers: List[dict] = field(default_factory=list)
    improvement_plan: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    llm_used: bool = False

    def to_dict(self) -> dict:
        return {
            "overall": self.overall,
            "strengths": self.strengths,
            "weaknesses": self.weaknesses,
            "missed_points": self.missed_points,
            "model_answers": self.model_answers,
            "improvement_plan": self.improvement_plan,
            "references": self.references,
            "llm_used": self.llm_used,
        }


class Retrospective:
    def __init__(self, gateway: Optional[Gateway] = None, tools: Optional[ToolRegistry] = None) -> None:
        self.gateway = gateway
        self.tools = tools

    async def run(self, transcript: str, job_text: str = "", company: str = "",
                  tracer: Optional[Tracer] = None) -> RetrospectiveResult:
        tracer = tracer or Tracer()
        span = tracer.start_span("retrospective", SpanKind.AGENT,
                                 has_llm=llm_available(self.gateway))
        try:
            if not llm_available(self.gateway):
                result = self._offline(transcript)
                tracer.end_span(span, SpanStatus.OK, mode="offline")
                return result

            tools = self.tools.subset(["web_search"]) if self.tools else ToolRegistry()
            agent = Agent(self.gateway, tools, tracer, system=_SYSTEM,
                          name="retrospective", temperature=0.4, parent_span_id=span.id)
            prompt = (
                f"目标公司：{company or '未知'}\n目标岗位JD：\n{job_text or '未提供'}\n\n"
                f"面试记录：\n{transcript}\n\n请对这场面试做复盘。"
            )
            out = await agent.run(prompt)
            data = extract_json(out.output) or {}
            result = self._from_json(data)
            result.llm_used = True
            if not result.overall and not result.strengths:
                result = self._offline(transcript)
                result.llm_used = True
            tracer.end_span(span, SpanStatus.OK, mode="agentic")
            return result
        except Exception as exc:  # noqa: BLE001
            tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
            raise

    @staticmethod
    def _from_json(data: dict) -> RetrospectiveResult:
        if not isinstance(data, dict):
            return RetrospectiveResult()
        return RetrospectiveResult(
            overall=str(data.get("overall", "")),
            strengths=[str(x) for x in data.get("strengths", [])],
            weaknesses=[str(x) for x in data.get("weaknesses", [])],
            missed_points=[str(x) for x in data.get("missed_points", [])],
            model_answers=[x for x in data.get("model_answers", []) if isinstance(x, dict)],
            improvement_plan=[str(x) for x in data.get("improvement_plan", [])],
            references=[str(x) for x in data.get("references", [])],
        )

    @staticmethod
    def _offline(transcript: str) -> RetrospectiveResult:
        answers = [ln for ln in transcript.splitlines() if ln.strip().startswith("候选人")]
        avg_len = sum(len(a) for a in answers) / len(answers) if answers else 0
        strengths, weaknesses, plan = [], [], []
        if avg_len >= 60:
            strengths.append("回答较为充实，展开了细节。")
        else:
            weaknesses.append("部分回答偏简短，建议用 STAR 结构补充情境与结果。")
        if any(any(ch.isdigit() for ch in a) for a in answers):
            strengths.append("回答中包含量化数据，具说服力。")
        else:
            weaknesses.append("回答缺少量化结果，建议加入可衡量的指标。")
        plan += [
            "用 STAR 法则重述每个项目，突出你的具体行动与可量化结果。",
            "针对岗位硬性技能准备 2-3 个深度案例，能经得起追问。",
            "复盘每个未答好的问题，整理成标准答案库。",
        ]
        return RetrospectiveResult(
            overall="离线复盘（未启用大模型）：基于回答长度与量化情况的启发式评估。",
            strengths=strengths, weaknesses=weaknesses, improvement_plan=plan, llm_used=False,
        )
