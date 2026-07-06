"""Core data models used across the jobseeker agent."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class Resume:
    """A structured representation of a candidate's profile."""

    name: str = ""
    title: str = ""
    summary: str = ""
    years_experience: float = 0.0
    skills: List[str] = field(default_factory=list)
    experiences: List[str] = field(default_factory=list)
    education: List[str] = field(default_factory=list)
    highlights: List[str] = field(default_factory=list)
    contact: Dict[str, str] = field(default_factory=dict)
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class JobPosting:
    """A structured representation of a job description (JD)."""

    title: str = ""
    company: str = ""
    location: str = ""
    seniority: str = ""
    min_years: float = 0.0
    required_skills: List[str] = field(default_factory=list)
    preferred_skills: List[str] = field(default_factory=list)
    responsibilities: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def all_skills(self) -> List[str]:
        seen: Dict[str, None] = {}
        for skill in self.required_skills + self.preferred_skills:
            seen.setdefault(skill, None)
        return list(seen.keys())


@dataclass
class MatchResult:
    """The outcome of comparing a resume against a job posting."""

    score: float = 0.0  # 0..100 overall fit
    skill_score: float = 0.0
    experience_score: float = 0.0
    matched_skills: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    missing_preferred: List[str] = field(default_factory=list)
    strengths: List[str] = field(default_factory=list)
    gaps: List[str] = field(default_factory=list)
    recommendation: str = ""

    def to_dict(self) -> Dict[str, Any]:
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

    match: Optional[MatchResult] = None
    cover_letter: str = ""
    outreach_message: str = ""
    interview_questions: List[str] = field(default_factory=list)
    tips: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        if self.match is not None:
            data["match"] = self.match.to_dict()
        return data
