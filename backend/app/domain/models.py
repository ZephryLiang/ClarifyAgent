"""Core data models used across the jobseeker agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Resume:
    """A structured representation of a candidate's profile."""

    name: str = ""
    title: str = ""
    summary: str = ""
    years_experience: float = 0.0
    skills: list[str] = field(default_factory=list)
    experiences: list[str] = field(default_factory=list)
    education: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    contact: dict[str, str] = field(default_factory=dict)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobPosting:
    """A structured representation of a job description (JD)."""

    title: str = ""
    company: str = ""
    location: str = ""
    seniority: str = ""
    min_years: float = 0.0
    required_skills: list[str] = field(default_factory=list)
    preferred_skills: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def all_skills(self) -> list[str]:
        seen: dict[str, None] = {}
        for skill in self.required_skills + self.preferred_skills:
            seen.setdefault(skill, None)
        return list(seen.keys())


@dataclass
class MatchResult:
    """The outcome of comparing a resume against a job posting."""

    score: float = 0.0  # 0..100 overall fit
    skill_score: float = 0.0
    experience_score: float = 0.0
    matched_skills: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    missing_preferred: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def verdict(self) -> str:
        if self.score >= 75:
            return "强烈推荐投递 (Strong match)"
        if self.score >= 55:
            return "建议投递 (Good match)"
        if self.score >= 35:
            return "可以尝试 (Worth a shot)"
        return "匹配度较低 (Low match)"


@dataclass
class ApplicationKit:
    """A complete application package produced for a single job."""

    match: MatchResult | None = None
    cover_letter: str = ""
    outreach_message: str = ""
    interview_questions: list[str] = field(default_factory=list)
    tips: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if self.match is not None:
            data["match"] = self.match.to_dict()
        return data
