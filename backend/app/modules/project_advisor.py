"""Production-grade project proposal from tech research."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from .base import llm_available
from .tech_research import TechResearchDigest


@dataclass
class ProjectProposal:
    title: str
    theme: str
    pain_points: list[str] = field(default_factory=list)
    mvp_scope: list[str] = field(default_factory=list)
    stack: list[str] = field(default_factory=list)
    interview_talking_points: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    warning: str = "需用户真实完成项目后方可写入简历。"

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "theme": self.theme,
            "pain_points": self.pain_points,
            "mvp_scope": self.mvp_scope,
            "stack": self.stack,
            "interview_talking_points": self.interview_talking_points,
            "citations": self.citations,
            "warning": self.warning,
        }


class ProjectAdvisor:
    def __init__(self, gateway: Gateway | None = None) -> None:
        self.gateway = gateway

    async def propose_from_research(
        self, theme: str, digest: TechResearchDigest, tracer: Tracer | None = None,
    ) -> ProjectProposal:
        citations = [f"{s.source_type}: {s.snippet[:80]}…" for s in digest.sources[:3]]
        proposal = ProjectProposal(
            title=f"Mini {theme.title()} Project",
            theme=theme,
            pain_points=[s.signals[0] if s.signals else s.source_type for s in digest.sources[:3]],
            mvp_scope=[
                "Week 1: 核心 loop + 状态持久化",
                "Week 2: 可观测性 + 失败恢复",
            ],
            stack=["Python/Go", "SQLite/Redis", "OpenTelemetry"],
            interview_talking_points=[
                f"{theme} 的生产痛点与 tradeoff",
                "durable execution 设计",
            ],
            citations=citations,
        )
        if not llm_available(self.gateway):
            return proposal

        assert self.gateway is not None
        agent = Agent(
            self.gateway, ToolRegistry(), tracer or Tracer(),
            system="基于调研摘要设计 production-grade side project，输出简洁 JSON 字段。",
            name="project-advisor", temperature=0.4,
        )
        import json
        prompt = f"主题: {theme}\n调研:\n{json.dumps(digest.to_dict(), ensure_ascii=False)[:2000]}"
        result = await agent.run(prompt)
        proposal.interview_talking_points.append(result.output[:200])
        return proposal
