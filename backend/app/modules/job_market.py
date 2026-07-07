"""Cross-company job market aggregation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JobMarketReport:
    companies: list[str] = field(default_factory=list)
    role_types: dict[str, int] = field(default_factory=dict)
    top_skills: list[dict] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "companies": self.companies,
            "role_types": self.role_types,
            "top_skills": self.top_skills,
            "summary": self.summary,
        }


class JobMarketAggregator:
    def aggregate(self, workspace: dict[str, Any]) -> JobMarketReport:
        assessments = workspace.get("role_assessments") or []
        companies = [a.get("role_type_label", "") for a in assessments]
        role_types = Counter(a.get("role_type", "unknown") for a in assessments)
        jobs = workspace.get("jobs") or []
        skill_counter: Counter[str] = Counter()
        for j in jobs:
            from ..domain import parse_job_text
            job = parse_job_text(j.get("text", ""))
            for s in job.required_skills:
                skill_counter[s] += 1
        top = [{"skill": k, "count": v} for k, v in skill_counter.most_common(10)]
        summary = f"已分析 {len(assessments)} 个岗位评估、{len(jobs)} 份 JD。"
        if top:
            summary += " 高频技能: " + ", ".join(t["skill"] for t in top[:5]) + "。"
        return JobMarketReport(
            companies=[j.get("company", "") for j in jobs],
            role_types=dict(role_types),
            top_skills=top,
            summary=summary,
        )
