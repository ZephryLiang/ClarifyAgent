"""Tests for Copilot chat session and offline flows."""

from __future__ import annotations

import pytest

from app.modules.copilot import create_session
from app.modules.copilot.runner import JobSeekerCopilot
from app.modules.requirement_synth import RequirementSynthesizer
from app.modules.learning_plan import LearningPlanGenerator
from app.modules.jd_analyzer import JDAnalyzer
from app.service import AppServices


SAMPLE_JD = """
字节跳动 Agent Runtime 后端
任职要求：Go Python 分布式系统 Kubernetes
职责：构建 agent 执行引擎 checkpoint
"""

SAMPLE_RESUME = """
工作经历
项目经验：订单系统 高并发
技能：Python Redis MySQL
"""


@pytest.mark.asyncio
async def test_copilot_offline_captures_jd():
    svc = AppServices()
    session = create_session()
    turn = await svc.copilot.handle_message(session, SAMPLE_JD)
    assert "JD" in turn.assistant_message or "保存" in turn.assistant_message
    assert session["workspace"].get("job_text")


@pytest.mark.asyncio
async def test_jd_analyzer_offline():
    svc = AppServices()
    analysis = await svc.jd_analyzer.run(SAMPLE_JD)
    assert analysis.hard_skills or analysis.summary


def test_requirement_synthesis_and_plan():
    ws = {
        "jobs": [
            {"text": SAMPLE_JD},
            {"text": SAMPLE_JD.replace("字节", "腾讯")},
        ],
        "resume_text": SAMPLE_RESUME,
    }
    matrix = RequirementSynthesizer().synthesize(ws)
    assert matrix.job_count == 2
    assert matrix.rows
    plan = LearningPlanGenerator().generate(
        matrix, {"weeks": 4, "hours_per_week": 10}, SAMPLE_RESUME,
    )
    assert plan.phases
    assert plan.time_budget["total_hours"] == 40


@pytest.mark.asyncio
async def test_chat_session_persistence():
    svc = AppServices()
    session = create_session()
    svc.store.chat_save(session["id"], session)
    loaded = svc.store.chat_get(session["id"])
    assert loaded is not None
    assert loaded["id"] == session["id"]
