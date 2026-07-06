"""Score how well a resume matches a job posting."""

from __future__ import annotations

from typing import List, Set

from .models import JobPosting, MatchResult, Resume
from .skills import normalize_skills

# Weights for the overall score. Skills dominate, experience adjusts.
_SKILL_WEIGHT = 0.75
_EXPERIENCE_WEIGHT = 0.25

# Within the skill score, required skills matter far more than preferred ones.
_REQUIRED_WEIGHT = 0.8
_PREFERRED_WEIGHT = 0.2


def _skill_set(skills: List[str]) -> Set[str]:
    return {s.lower() for s in normalize_skills(skills)}


def _coverage(candidate: Set[str], target: List[str]) -> float:
    if not target:
        return 1.0
    target_set = {s.lower() for s in target}
    hit = len(candidate & target_set)
    return hit / len(target_set)


def compute_match(resume: Resume, job: JobPosting) -> MatchResult:
    """Compare ``resume`` against ``job`` and return a :class:`MatchResult`."""

    candidate = _skill_set(resume.skills)

    required = job.required_skills
    preferred = job.preferred_skills

    required_cov = _coverage(candidate, required)
    preferred_cov = _coverage(candidate, preferred)

    skill_score = 100.0 * (
        _REQUIRED_WEIGHT * required_cov + _PREFERRED_WEIGHT * preferred_cov
    )

    # Experience score: full marks if the candidate meets/exceeds the minimum;
    # otherwise scaled proportionally. No minimum => neutral full score.
    if job.min_years <= 0:
        experience_score = 100.0
    else:
        ratio = resume.years_experience / job.min_years
        experience_score = max(0.0, min(1.0, ratio)) * 100.0

    score = _SKILL_WEIGHT * skill_score + _EXPERIENCE_WEIGHT * experience_score

    matched = [s for s in job.all_skills if s.lower() in candidate]
    missing_required = [s for s in required if s.lower() not in candidate]
    missing_preferred = [s for s in preferred if s.lower() not in candidate]

    strengths: List[str] = []
    if matched:
        strengths.append("覆盖岗位技能: " + ", ".join(matched))
    if job.min_years and resume.years_experience >= job.min_years:
        strengths.append(
            f"经验满足要求 ({resume.years_experience:g} 年 ≥ {job.min_years:g} 年)"
        )
    extra = [s for s in resume.skills if s.lower() not in {k.lower() for k in job.all_skills}]
    if extra:
        strengths.append("额外技能: " + ", ".join(extra[:8]))

    gaps: List[str] = []
    if missing_required:
        gaps.append("缺少硬性技能: " + ", ".join(missing_required))
    if missing_preferred:
        gaps.append("缺少加分技能: " + ", ".join(missing_preferred))
    if job.min_years and resume.years_experience < job.min_years:
        gaps.append(
            f"经验不足 ({resume.years_experience:g} 年 < {job.min_years:g} 年)"
        )

    result = MatchResult(
        score=round(score, 1),
        skill_score=round(skill_score, 1),
        experience_score=round(experience_score, 1),
        matched_skills=matched,
        missing_required=missing_required,
        missing_preferred=missing_preferred,
        strengths=strengths,
        gaps=gaps,
    )
    result.recommendation = _build_recommendation(result, job)
    return result


def _build_recommendation(result: MatchResult, job: JobPosting) -> str:
    parts = [result.verdict + "."]
    if result.missing_required:
        parts.append(
            "投递前建议补充或在简历中突出: " + ", ".join(result.missing_required) + "。"
        )
    else:
        parts.append("你已覆盖全部硬性技能，可自信投递。")
    if result.missing_preferred:
        parts.append("若时间允许，可学习加分项: " + ", ".join(result.missing_preferred) + "。")
    return " ".join(parts)
