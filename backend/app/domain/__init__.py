"""Pure, dependency-free domain logic: parsing, skills, matching, models."""

from .models import Resume, JobPosting, MatchResult, ApplicationKit
from .resume import parse_resume_text, parse_resume_json, load_resume
from .jobs import parse_job_text, parse_job_json, load_job
from .matcher import compute_match

__all__ = [
    "Resume",
    "JobPosting",
    "MatchResult",
    "ApplicationKit",
    "parse_resume_text",
    "parse_resume_json",
    "load_resume",
    "parse_job_text",
    "parse_job_json",
    "load_job",
    "compute_match",
]
