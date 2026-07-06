"""Parse a candidate resume / profile into a :class:`Resume`.

Two input shapes are supported:

* **JSON** — an object whose keys line up with :class:`Resume` fields. This is
  the most reliable form and is what the CLI writes out.
* **Free-form text / Markdown** — a best-effort parser that recognises common
  section headers (both English and Chinese) such as "Skills / 技能",
  "Experience / 经历", "Education / 教育".
"""

from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

from .models import Resume
from .skills import extract_skills, normalize_skills

# Section header keywords mapped onto the Resume field they populate.
_SECTION_KEYWORDS: Dict[str, List[str]] = {
    "summary": ["summary", "profile", "about", "简介", "自我评价", "个人简介"],
    "skills": ["skills", "technical skills", "技能", "技术栈", "专业技能"],
    "experiences": ["experience", "work experience", "employment", "经历", "工作经历", "项目经历"],
    "education": ["education", "学历", "教育", "教育背景"],
    "highlights": ["highlights", "achievements", "亮点", "成就"],
}

_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years|year|yrs|年)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?:(?:\+?\d{1,3}[\s-]?)?(?:\d[\s-]?){7,12}\d)")


def _match_section(line: str) -> Optional[str]:
    stripped = line.strip().lstrip("#").strip().rstrip(":：").strip().lower()
    if not stripped:
        return None
    for field, keywords in _SECTION_KEYWORDS.items():
        for kw in keywords:
            if stripped == kw or stripped.startswith(kw):
                return field
    return None


def _clean_bullet(line: str) -> str:
    return line.strip().lstrip("-*•·").strip()


def parse_resume_text(text: str) -> Resume:
    """Parse free-form resume text into a :class:`Resume`."""

    resume = Resume(raw_text=text)
    lines = text.splitlines()

    # First non-empty line is treated as the candidate name; a following line
    # containing a job-title-like phrase becomes the title.
    non_empty = [ln.strip() for ln in lines if ln.strip()]
    if non_empty:
        resume.name = non_empty[0].lstrip("#").strip()
    if len(non_empty) > 1 and _match_section(non_empty[1]) is None:
        resume.title = non_empty[1]

    current: Optional[str] = None
    buckets: Dict[str, List[str]] = {k: [] for k in _SECTION_KEYWORDS}

    for line in lines:
        section = _match_section(line)
        if section is not None:
            current = section
            continue
        if current is None:
            continue
        content = _clean_bullet(line)
        if content:
            buckets[current].append(content)

    resume.summary = " ".join(buckets["summary"]).strip()
    resume.experiences = buckets["experiences"]
    resume.education = buckets["education"]
    resume.highlights = buckets["highlights"]

    # Skills: explicit skills section (comma/、 separated) + skills mined from
    # the entire document.
    explicit: List[str] = []
    for entry in buckets["skills"]:
        explicit.extend(re.split(r"[,，、/|]", entry))
    mined = extract_skills(text)
    resume.skills = normalize_skills([s for s in explicit if s.strip()] + mined)

    # Experience in years — take the maximum number mentioned.
    years = [float(m) for m in _YEARS_RE.findall(text)]
    if years:
        resume.years_experience = max(years)

    contact: Dict[str, str] = {}
    email = _EMAIL_RE.search(text)
    if email:
        contact["email"] = email.group(0)
    resume.contact = contact

    return resume


def parse_resume_json(data: str | dict) -> Resume:
    """Parse a JSON string / dict into a :class:`Resume`."""

    obj = json.loads(data) if isinstance(data, str) else dict(data)
    known = {f for f in Resume().__dict__}
    filtered = {k: v for k, v in obj.items() if k in known}
    resume = Resume(**filtered)
    resume.skills = normalize_skills(resume.skills)
    if not resume.skills and resume.raw_text:
        resume.skills = extract_skills(resume.raw_text)
    return resume


def load_resume(path: str) -> Resume:
    """Load a resume from ``path`` (``.json`` uses the JSON parser)."""

    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read()
    if path.lower().endswith(".json"):
        return parse_resume_json(content)
    return parse_resume_text(content)
