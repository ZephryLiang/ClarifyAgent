"""Deterministic built-in tools backed by the pure domain layer."""

from __future__ import annotations

import json
from typing import Any, Dict

from ..domain import compute_match, parse_job_text, parse_resume_text
from ..harness.tools import Tool, ToolResult


class SkillMatchTool(Tool):
    name = "skill_match"
    description = (
        "对给定的简历文本与岗位JD文本做确定性技能匹配打分（无需大模型），"
        "返回综合匹配度、已匹配/缺失技能。适合快速客观评估。"
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "resume_text": {"type": "string", "description": "简历纯文本"},
            "job_text": {"type": "string", "description": "岗位JD纯文本"},
        },
        "required": ["resume_text", "job_text"],
    }

    async def run(self, resume_text: str, job_text: str) -> ToolResult:
        resume = parse_resume_text(resume_text)
        job = parse_job_text(job_text)
        match = compute_match(resume, job)
        payload = {
            "score": match.score,
            "skill_score": match.skill_score,
            "experience_score": match.experience_score,
            "verdict": match.verdict,
            "matched_skills": match.matched_skills,
            "missing_required": match.missing_required,
            "missing_preferred": match.missing_preferred,
        }
        return ToolResult(content=json.dumps(payload, ensure_ascii=False, indent=2), data=match)
