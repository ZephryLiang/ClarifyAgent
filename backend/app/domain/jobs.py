"""Parse a job posting (JD) into a :class:`JobPosting`."""

from __future__ import annotations

import json
import re

from .models import JobPosting
from .skills import extract_skills, normalize_skills

_SECTION_KEYWORDS: dict[str, list[str]] = {
    "required_skills": [
        "requirements", "required", "qualifications", "must have",
        "任职要求", "岗位要求", "职位要求", "必备技能", "硬性要求",
    ],
    "preferred_skills": [
        "preferred", "nice to have", "bonus", "plus", "加分项", "优先", "加分",
    ],
    "responsibilities": [
        "responsibilities", "duties", "what you'll do", "role",
        "岗位职责", "工作职责", "职责", "工作内容",
    ],
}

_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years|year|yrs|年)", re.IGNORECASE)

_SENIORITY_KEYWORDS = {
    "intern": ["intern", "实习"],
    "junior": ["junior", "entry", "初级", "应届"],
    "mid": ["mid", "intermediate", "中级"],
    "senior": ["senior", "sr.", "高级", "资深"],
    "lead": ["lead", "principal", "staff", "架构", "负责人", "leader"],
}


def _match_section(line: str) -> str | None:
    stripped = line.strip().lstrip("#").strip().rstrip(":：").strip().lower()
    if not stripped:
        return None
    for field, keywords in _SECTION_KEYWORDS.items():
        for kw in keywords:
            if kw in stripped:
                return field
    return None


def _clean_bullet(line: str) -> str:
    return line.strip().lstrip("-*•·0123456789.、)")


def _detect_seniority(text: str) -> str:
    lower = text.lower()
    for level, keywords in _SENIORITY_KEYWORDS.items():
        for kw in keywords:
            if kw in lower:
                return level
    return ""


def parse_job_text(text: str) -> JobPosting:
    """Parse free-form job description text into a :class:`JobPosting`."""

    job = JobPosting(raw_text=text)
    lines = text.splitlines()
    non_empty = [ln.strip() for ln in lines if ln.strip()]
    if non_empty:
        job.title = non_empty[0].lstrip("#").strip()

    # company / location heuristics from an early "Company: X" style line.
    for line in non_empty[:6]:
        low = line.lower()
        if low.startswith(("company", "公司")):
            job.company = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif low.startswith(("location", "地点", "工作地点")):
            job.location = line.split(":", 1)[-1].split("：", 1)[-1].strip()

    current: str | None = None
    buckets: dict[str, list[str]] = {k: [] for k in _SECTION_KEYWORDS}
    for line in lines:
        section = _match_section(line)
        if section is not None:
            current = section
            continue
        if current is None:
            continue
        content = _clean_bullet(line).strip()
        if content:
            buckets[current].append(content)

    job.responsibilities = buckets["responsibilities"]

    required_text = " \n ".join(buckets["required_skills"])
    preferred_text = " \n ".join(buckets["preferred_skills"])

    job.required_skills = normalize_skills(extract_skills(required_text))
    job.preferred_skills = normalize_skills(
        [s for s in extract_skills(preferred_text) if s not in job.required_skills]
    )

    # If no explicit requirement section was found, mine skills from the whole
    # posting so matching still works.
    if not job.required_skills and not job.preferred_skills:
        job.required_skills = normalize_skills(extract_skills(text))

    years = [float(m) for m in _YEARS_RE.findall(required_text or text)]
    if years:
        job.min_years = min(years)

    job.seniority = _detect_seniority(text)
    job.keywords = extract_skills(text)
    return job


def parse_job_json(data: str | dict) -> JobPosting:
    obj = json.loads(data) if isinstance(data, str) else dict(data)
    known = {f for f in JobPosting().__dict__}
    filtered = {k: v for k, v in obj.items() if k in known}
    job = JobPosting(**filtered)
    job.required_skills = normalize_skills(job.required_skills)
    job.preferred_skills = normalize_skills(job.preferred_skills)
    return job


def load_job(path: str) -> JobPosting:
    with open(path, encoding="utf-8") as fh:
        content = fh.read()
    if path.lower().endswith(".json"):
        return parse_job_json(content)
    return parse_job_text(content)
