"""Multi-source tech research with source scoring."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..gateway.registry import Gateway
from ..harness import Orchestrator, SubagentTask, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from .base import llm_available


@dataclass
class ScoredSource:
    title: str
    url: str
    snippet: str
    source_type: str
    score: float
    signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source_type": self.source_type,
            "score": self.score,
            "signals": self.signals,
        }


@dataclass
class TechResearchDigest:
    theme: str
    sources: list[ScoredSource] = field(default_factory=list)
    high_value_count: int = 0
    llm_used: bool = False

    def to_dict(self) -> dict:
        return {
            "theme": self.theme,
            "sources": [s.to_dict() for s in self.sources],
            "high_value_count": self.high_value_count,
            "llm_used": self.llm_used,
        }


def score_source(title: str, snippet: str, source_type: str) -> tuple[float, list[str]]:
    text = (title + " " + snippet).lower()
    signals: list[str] = []
    score = 40.0
    prod_kw = ["production", "scale", "latency", "reliability", "failure", "生产", "分布式", "容错"]
    if any(k in text for k in prod_kw):
        score += 25
        signals.append("production_pain")
    if source_type == "blog" and any(k in text for k in ["engineering", "meta", "uber", "google"]):
        score += 15
        signals.append("authority")
    if source_type == "interview" and any(k in text for k in ["system design", "design", "架构"]):
        score += 10
        signals.append("interview_signal")
    if any(k in text for k in ["tutorial", "入门", "hello world", "beginner"]):
        score -= 20
        signals.append("generic_tutorial")
    return min(100.0, max(0.0, score)), signals


class TechResearchAgent:
    def __init__(self, gateway: Gateway | None = None, tools: ToolRegistry | None = None) -> None:
        self.gateway = gateway
        self.tools = tools

    async def run(self, theme: str, tracer: Tracer | None = None) -> TechResearchDigest:
        tracer = tracer or Tracer()
        span = tracer.start_span("tech-research", SpanKind.AGENT)
        digest = TechResearchDigest(theme=theme)

        if not (llm_available(self.gateway) and self.tools):
            digest.sources.append(ScoredSource(
                title="离线提示", url="", snippet="配置 LLM 与 web_search 以运行多源调研。",
                source_type="offline", score=0,
            ))
            tracer.end_span(span, SpanStatus.OK, mode="offline")
            return digest

        assert self.gateway is not None and self.tools is not None
        orchestrator = Orchestrator(self.gateway, self.tools, tracer, max_iterations=3)
        queries = [
            ("papers", f"arxiv {theme} production"),
            ("blogs", f"{theme} engineering blog production"),
            ("github", f"github {theme} open source production"),
            ("interviews", f"{theme} system design interview production"),
        ]
        tasks = [
            SubagentTask(
                name=f"research-{st}",
                system="用 web_search 检索并列出关键发现，简洁。",
                prompt=f"搜索并摘要: {q}",
                tool_names=["web_search"],
            )
            for st, q in queries
        ]
        outcomes = await orchestrator.run_parallel(tasks, parent_span_id=span.id)
        for (st, _), outcome in zip(queries, outcomes, strict=False):
            text = outcome.output if outcome.ok else ""
            score, signals = score_source(st, text[:200], st)
            digest.sources.append(ScoredSource(
                title=f"{st} research",
                url="",
                snippet=text[:500],
                source_type=st,
                score=score,
                signals=signals,
            ))
        digest.sources = [s for s in digest.sources if s.score >= 55]
        digest.sources.sort(key=lambda s: s.score, reverse=True)
        digest.high_value_count = sum(1 for s in digest.sources if s.score >= 75)
        digest.llm_used = True
        tracer.end_span(span, SpanStatus.OK, sources=len(digest.sources))
        return digest
