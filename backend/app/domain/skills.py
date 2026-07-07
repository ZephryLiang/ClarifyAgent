"""Skill taxonomy and lightweight keyword extraction.

The matcher relies on recognising skills mentioned in free-form resume and job
text. Rather than depend on a heavy NLP stack, we keep a curated dictionary of
common technical skills together with their aliases. This is intentionally easy
to extend — add new canonical skills or aliases and the whole pipeline benefits.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

# Canonical skill -> list of aliases (all matched case-insensitively).
# The canonical name is what we surface to the user.
SKILL_ALIASES: dict[str, list[str]] = {
    "Python": ["python", "py"],
    "Java": ["java"],
    "JavaScript": ["javascript", "js", "es6"],
    "TypeScript": ["typescript", "ts"],
    "Go": ["golang", "go"],
    "Rust": ["rust"],
    "C++": ["c++", "cpp"],
    "C": ["c language", "c programming"],
    "C#": ["c#", "csharp"],
    "SQL": ["sql", "mysql", "postgresql", "postgres", "sqlite"],
    "NoSQL": ["nosql", "mongodb", "cassandra", "dynamodb"],
    "Redis": ["redis"],
    "React": ["react", "reactjs", "react.js"],
    "Vue": ["vue", "vuejs", "vue.js"],
    "Angular": ["angular", "angularjs"],
    "Node.js": ["node.js", "nodejs", "node"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi"],
    "Spring": ["spring", "spring boot", "springboot"],
    "Docker": ["docker", "containerization"],
    "Kubernetes": ["kubernetes", "k8s"],
    "AWS": ["aws", "amazon web services"],
    "GCP": ["gcp", "google cloud"],
    "Azure": ["azure"],
    "CI/CD": ["ci/cd", "cicd", "continuous integration", "continuous delivery"],
    "Terraform": ["terraform"],
    "Linux": ["linux", "unix"],
    "Git": ["git", "github", "gitlab"],
    "Machine Learning": ["machine learning", "ml", "机器学习"],
    "Deep Learning": ["deep learning", "深度学习", "neural network"],
    "PyTorch": ["pytorch"],
    "TensorFlow": ["tensorflow"],
    "NLP": ["nlp", "natural language processing", "自然语言处理"],
    "LLM": ["llm", "large language model", "大模型", "gpt"],
    "Data Analysis": ["data analysis", "数据分析", "pandas", "numpy"],
    "Data Engineering": ["data engineering", "etl", "数据工程"],
    "Spark": ["spark", "pyspark"],
    "Kafka": ["kafka"],
    "GraphQL": ["graphql"],
    "REST": ["rest", "restful", "rest api"],
    "Microservices": ["microservices", "微服务"],
    "System Design": ["system design", "系统设计", "architecture"],
    "Agile": ["agile", "scrum", "敏捷"],
    "Product Management": ["product management", "产品经理", "产品管理"],
    "Project Management": ["project management", "项目管理"],
    "Communication": ["communication", "沟通"],
    "Leadership": ["leadership", "领导力", "team lead"],
    "HTML/CSS": ["html", "css", "html5", "css3"],
    "Testing": ["testing", "unit test", "pytest", "junit", "测试"],
}

# Precompute alias -> canonical for fast lookup.
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for _canonical, _aliases in SKILL_ALIASES.items():
    _ALIAS_TO_CANONICAL[_canonical.lower()] = _canonical
    for _alias in _aliases:
        _ALIAS_TO_CANONICAL[_alias.lower()] = _canonical


def _alias_pattern(alias: str) -> re.Pattern:
    """Build a word-boundary aware regex for an alias.

    Plain ``\\b`` boundaries do not behave well around symbols such as ``+`` or
    ``#`` (``c++``, ``c#``), so we anchor on non-alphanumeric characters or the
    string ends instead.
    """

    escaped = re.escape(alias)
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9+#.])", re.IGNORECASE)


# Cache compiled patterns keyed by alias.
_PATTERN_CACHE: dict[str, re.Pattern] = {
    alias: _alias_pattern(alias) for alias in _ALIAS_TO_CANONICAL
}


def extract_skills(text: str) -> list[str]:
    """Return the canonical skills detected in ``text`` (order preserved)."""

    if not text:
        return []

    found: dict[str, None] = {}
    for alias, canonical in _ALIAS_TO_CANONICAL.items():
        pattern = _PATTERN_CACHE[alias]
        if pattern.search(text):
            found.setdefault(canonical, None)
    return list(found.keys())


def normalize_skills(skills: Iterable[str]) -> list[str]:
    """Map an iterable of arbitrary skill strings onto canonical names.

    Unknown skills are kept as-is (title-stripped) so that user-provided skills
    are never silently dropped.
    """

    result: dict[str, None] = {}
    for skill in skills:
        if not skill:
            continue
        key = skill.strip()
        canonical = _ALIAS_TO_CANONICAL.get(key.lower(), key)
        result.setdefault(canonical, None)
    return list(result.keys())


def known_skills() -> list[str]:
    """Return the list of canonical skills the taxonomy understands."""

    return sorted(SKILL_ALIASES.keys())
