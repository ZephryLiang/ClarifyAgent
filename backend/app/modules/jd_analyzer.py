"""Lightweight JD-only analysis (no resume, no web search)."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import parse_job_text
from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from .base import extract_json, llm_available


@dataclass
class JDAnalysis:
    company: str = ""
    title: str = ""
    hard_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    role_type_guess: str = ""
    summary: str = ""
    min_years: float = 0.0
    llm_used: bool = False

    def to_dict(self) -> dict:
        return {
            "company": self.company,
            "title": self.title,
            "hard_skills": self.hard_skills,
            "preferred_skills": self.preferred_skills,
            "responsibilities": self.responsibilities[:8],
            "role_type_guess": self.role_type_guess,
            "summary": self.summary,
            "min_years": self.min_years,
            "llm_used": self.llm_used,
        }


class JDAnalyzer:
    def __init__(self, gateway: Gateway | None = None) -> None:
        self.gateway = gateway

    async def run(self, job_text: str, tracer: Tracer | None = None) -> JDAnalysis:
        tracer = tracer or Tracer()
        span = tracer.start_span("jd-analysis", SpanKind.AGENT, has_llm=llm_available(self.gateway))
        job = parse_job_text(job_text)
        base = JDAnalysis(
            company=job.company,
            title=job.title,
            hard_skills=job.required_skills[:20],
            preferred_skills=job.preferred_skills[:15],
            responsibilities=job.responsibilities[:8],
            min_years=job.min_years,
            role_type_guess=_guess_role_type(job_text),
            summary=_offline_summary(job),
            llm_used=False,
        )
        if not llm_available(self.gateway):
            tracer.end_span(span, SpanStatus.OK, mode="offline")
            return base

        assert self.gateway is not None
        agent = Agent(
            self.gateway,
            ToolRegistry(),
            tracer,
            system="你是招聘 JD 分析专家。只基于给定 JD 文本解读，不编造。输出 JSON。",
            name="jd-analyzer",
            temperature=0.3,
            parent_span_id=span.id,
        )
        prompt = (
            "解读以下 JD，输出 JSON："
            '{"summary":"...", "role_type_guess":"...", "implicit_expectations":["..."]}\n\n'
            f"{job_text[:6000]}"
        )
        result = await agent.run(prompt)
        data = extract_json(result.output) or {}
        base.summary = str(data.get("summary") or base.summary)
        base.role_type_guess = str(data.get("role_type_guess") or base.role_type_guess)
        base.llm_used = True
        tracer.end_span(span, SpanStatus.OK, mode="agentic")
        return base


def _guess_role_type(text: str) -> str:
    lower = text.lower()
    if "agent" in lower and ("runtime" in lower or "harness" in lower):
        return "agent_runtime"
    if "platform" in lower or "infra" in lower:
        return "backend_platform"
    if "machine learning" in lower or "ml " in lower:
        return "ml_engineering"
    return "backend_general"


def _offline_summary(job) -> str:
    parts = [f"「{job.title or '岗位'}」@ {job.company or '未知公司'}。"]
    if job.required_skills:
        parts.append("硬性技能: " + ", ".join(job.required_skills[:8]) + ".")
    if job.min_years:
        parts.append(f"经验要求约 {job.min_years:g} 年。")
    return " ".join(parts)
