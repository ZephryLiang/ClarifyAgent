"""Tests for the dependency-free domain layer."""

from app.domain import compute_match, parse_job_text, parse_resume_text
from app.domain.skills import extract_skills, normalize_skills


def test_extract_skills_handles_symbols_and_aliases():
    skills = extract_skills("I code in Python, C++ and use k8s with golang")
    assert "Python" in skills
    assert "C++" in skills
    assert "Kubernetes" in skills
    assert "Go" in skills


def test_normalize_skills_maps_aliases_and_dedupes():
    result = normalize_skills(["py", "Python", "js"])
    assert result.count("Python") == 1
    assert "JavaScript" in result


def test_parse_resume_extracts_sections():
    text = """# 张三
后端工程师

## 技能
Python、Docker、Kubernetes

## 工作经历
- 5 年后端经验，主导系统重构
"""
    resume = parse_resume_text(text)
    assert resume.name == "张三"
    assert "Python" in resume.skills
    assert resume.years_experience == 5
    assert resume.experiences


def test_parse_job_splits_required_and_preferred():
    text = """高级工程师
任职要求:
- 精通 Python
- 熟悉 Kubernetes
加分项:
- 了解 Kafka
"""
    job = parse_job_text(text)
    assert "Python" in job.required_skills
    assert "Kafka" in job.preferred_skills
    assert "Kafka" not in job.required_skills


def test_compute_match_scores_and_gaps():
    resume = parse_resume_text("技能\nPython、Docker\n经历\n3 年经验")
    job = parse_job_text("岗位\n任职要求:\n- Python\n- Kubernetes\n- 3 年经验")
    match = compute_match(resume, job)
    assert 0 <= match.score <= 100
    assert "Kubernetes" in match.missing_required
    assert "Python" in match.matched_skills
    assert match.recommendation
