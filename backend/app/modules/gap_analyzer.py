"""Deep semantic gap analysis between resume and JD."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import compute_match, parse_job_text, parse_resume_text
from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from .base import extract_json, llm_available


@dataclass
class GapItem:
    theme: str
    severity: str
    bridge: str
    jd_evidence: str = ""
    resume_gap: str = ""

    def to_dict(self) -> dict:
        return {
            "theme": self.theme,
            "severity": self.severity,
            "bridge": self.bridge,
            "jd_evidence": self.jd_evidence,
            "resume_gap": self.resume_gap,
        }


@dataclass
class GapAnalysisResult:
    score: float = 0.0
    gaps: list[GapItem] = field(default_factory=list)
    reframe_candidates: list[dict] = field(default_factory=list)
    recommendation: str = ""
    llm_used: bool = False

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "gaps": [g.to_dict() for g in self.gaps],
            "reframe_candidates": self.reframe_candidates,
            "recommendation": self.recommendation,
            "llm_used": self.llm_used,
        }


class GapAnalyzer:
    def __init__(self, gateway: Gateway | None = None) -> None:
        self.gateway = gateway

    async def run(self, resume_text: str, job_text: str, tracer: Tracer | None = None) -> GapAnalysisResult:
        tracer = tracer or Tracer()
        span = tracer.start_span("gap-analysis", SpanKind.AGENT)
        resume = parse_resume_text(resume_text)
        job = parse_job_text(job_text)
        match = compute_match(resume, job)
        result = GapAnalysisResult(score=match.score, llm_used=False)

        for skill in match.missing_required[:5]:
            result.gaps.append(GapItem(
                theme=skill,
                severity="high",
                bridge="new_project" if match.score < 50 else "reframe",
                jd_evidence=f"JD 硬性要求: {skill}",
                resume_gap="简历技能列表未覆盖",
            ))

        if not llm_available(self.gateway):
            result.recommendation = match.recommendation
            tracer.end_span(span, SpanStatus.OK, mode="offline")
            return result

        assert self.gateway is not None
        agent = Agent(
            self.gateway, ToolRegistry(), tracer,
            system="分析简历与 JD 的语义 gap，输出 JSON。",
            name="gap-analyzer", temperature=0.3, parent_span_id=span.id,
        )
        prompt = (
            '输出 {"gaps":[{"theme","severity","bridge","jd_evidence","resume_gap"}],'
            '"reframe_candidates":[{"project","suggested_angle"}],"recommendation":"..."}\n\n'
            f"JD:\n{job_text[:3000]}\n\n简历:\n{resume_text[:3000]}"
        )
        out = await agent.run(prompt)
        data = extract_json(out.output) or {}
        for g in data.get("gaps") or []:
            if isinstance(g, dict):
                result.gaps.append(GapItem(
                    theme=str(g.get("theme", "")),
                    severity=str(g.get("severity", "medium")),
                    bridge=str(g.get("bridge", "reframe")),
                    jd_evidence=str(g.get("jd_evidence", "")),
                    resume_gap=str(g.get("resume_gap", "")),
                ))
        result.reframe_candidates = list(data.get("reframe_candidates") or [])
        result.recommendation = str(data.get("recommendation") or match.recommendation)
        result.llm_used = True
        tracer.end_span(span, SpanStatus.OK, mode="agentic")
        return result
