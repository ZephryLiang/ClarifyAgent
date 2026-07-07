"""Aggregate requirements across multiple JDs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from ..domain import parse_job_text, parse_resume_text, compute_match
from ..domain.skills import normalize_skills


@dataclass
class RequirementRow:
    topic: str
    jd_count: int
    coverage: float
    auto_tier: str
    effective_tier: str
    user_has: bool | None = None
    override_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "jd_count": self.jd_count,
            "coverage": self.coverage,
            "auto_tier": self.auto_tier,
            "effective_tier": self.effective_tier,
            "user_has": self.user_has,
            "override_reason": self.override_reason,
        }


@dataclass
class RequirementMatrix:
    job_count: int = 0
    rows: list[RequirementRow] = field(default_factory=list)
    overrides: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "job_count": self.job_count,
            "rows": [r.to_dict() for r in self.rows],
            "overrides": self.overrides,
        }


def _tier(coverage: float, user_has: bool | None) -> str:
    if coverage >= 0.7 and user_has is not False:
        return "P0"
    if coverage >= 0.4:
        return "P1"
    if coverage >= 0.2:
        return "P2"
    return "P3"


class RequirementSynthesizer:
    def synthesize(self, workspace: dict[str, Any]) -> RequirementMatrix:
        jobs = list(workspace.get("jobs") or [])
        if not jobs and workspace.get("job_text"):
            jobs = [{"text": workspace["job_text"]}]
        n = len(jobs)
        counter: Counter[str] = Counter()
        for j in jobs:
            job = parse_job_text(j.get("text") or workspace.get("job_text", ""))
            for s in normalize_skills(job.required_skills + job.preferred_skills):
                counter[s] += 1

        resume_skills: set[str] = set()
        if workspace.get("resume_text"):
            resume_skills = {s.lower() for s in parse_resume_text(workspace["resume_text"]).skills}

        overrides = dict(workspace.get("tier_overrides") or {})
        rows: list[RequirementRow] = []
        for topic, count in counter.most_common(25):
            cov = count / max(n, 1)
            user_has = topic.lower() in resume_skills if resume_skills else None
            auto = _tier(cov, user_has)
            effective = overrides.get(topic, auto)
            rows.append(RequirementRow(
                topic=topic,
                jd_count=count,
                coverage=round(cov, 2),
                auto_tier=auto,
                effective_tier=effective,
                user_has=user_has,
                override_reason=overrides.get(f"{topic}_reason", ""),
            ))
        return RequirementMatrix(job_count=n, rows=rows, overrides=overrides)
