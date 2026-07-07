"""Role type assessment with growth and tradeoffs."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..domain import parse_job_text
from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from .base import extract_json, llm_available, load_kb_relative
from .jd_analyzer import _guess_role_type


@dataclass
class RoleAssessment:
    role_type: str = ""
    role_type_label: str = ""
    growth: dict[str, str] = field(default_factory=dict)
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    fit_for_user: str = "medium"
    recommendation: str = ""
    tradeoffs: str = ""
    llm_used: bool = False

    def to_dict(self) -> dict:
        return {
            "role_type": self.role_type,
            "role_type_label": self.role_type_label,
            "growth": self.growth,
            "pros": self.pros,
            "cons": self.cons,
            "fit_for_user": self.fit_for_user,
            "recommendation": self.recommendation,
            "tradeoffs": self.tradeoffs,
            "llm_used": self.llm_used,
        }


_LABELS = {
    "agent_runtime": "Agent Infrastructure / Runtime",
    "backend_platform": "Backend Platform",
    "ml_engineering": "ML Engineering",
    "backend_general": "Backend General",
}


class RoleAssessor:
    def __init__(self, gateway: Gateway | None = None) -> None:
        self.gateway = gateway
        self._labels = dict(_LABELS)
        for line in load_kb_relative("roles", "taxonomy.md").splitlines():
            if "|" not in line:
                continue
            cells = [c.strip() for c in line.split("|") if c.strip()]
            if len(cells) >= 2 and cells[0] not in ("id", "---") and "_" in cells[0]:
                self._labels[cells[0]] = cells[1]

    async def run(self, job_text: str, company: str, tracer: Tracer | None = None) -> RoleAssessment:
        rtype = _guess_role_type(job_text)
        base = RoleAssessment(
            role_type=rtype,
            role_type_label=self._labels.get(rtype, rtype),
            growth={"learning": "high", "market_demand": "rising", "ceiling": "senior+"},
            pros=["技术深度可积累", "技能可迁移"],
            cons=["业务可见性因公司而异"],
            recommendation="值得进一步匹配分析后决定。",
            tradeoffs="深度技术 vs 业务影响力",
        )
        if not llm_available(self.gateway) or not job_text:
            return base

        assert self.gateway is not None
        agent = Agent(
            self.gateway, ToolRegistry(), tracer or Tracer(),
            system="评估岗位类型、成长性、利弊。输出 JSON。",
            name="role-assessor", temperature=0.3,
        )
        job = parse_job_text(job_text)
        prompt = f"公司: {company or job.company}\nJD:\n{job_text[:4000]}"
        out = await agent.run(prompt)
        data = extract_json(out.output) or {}
        base.pros = list(data.get("pros") or base.pros)
        base.cons = list(data.get("cons") or base.cons)
        base.recommendation = str(data.get("recommendation") or base.recommendation)
        base.tradeoffs = str(data.get("tradeoffs") or base.tradeoffs)
        base.llm_used = True
        return base
