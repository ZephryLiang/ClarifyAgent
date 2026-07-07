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
    svc.set_llm_mode("offline")
    session = create_session()
    long_jd = SAMPLE_JD + "\n" + ("熟悉 Go Python Kubernetes 分布式。\n" * 15)
    turn = await svc.copilot.handle_message(session, long_jd)
    assert "保存" in turn.assistant_message
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
async def test_copilot_propose_confirm_match_offline():
    """Offline path: proposal is created via tool; confirm consumes it."""
    from app.modules.copilot.context import CopilotContext
    from app.modules.copilot.tools import ProposeMatchTool, RunMatchTool
    from app.harness import Tracer

    svc = AppServices()
    session = create_session()
    session["workspace"]["resume_text"] = SAMPLE_RESUME
    session["workspace"]["job_text"] = SAMPLE_JD
    tracer = Tracer()
    ledger = svc.activity
    ctx = CopilotContext(session=session, services=svc, tracer=tracer, ledger=ledger)

    propose = ProposeMatchTool(ctx)
    prop_result = await propose.run()
    assert session.get("pending_proposal")
    prop_id = session["pending_proposal"]["id"]

    session["proposal_approved_id"] = prop_id
    run = RunMatchTool(ctx)
    run_result = await run.run(proposal_id=prop_id)
    assert not run_result.is_error
    assert any(a["kind"] == "match_report" for a in session.get("artifacts", []))


@pytest.mark.asyncio
async def test_chat_session_persistence():
    svc = AppServices()
    session = create_session()
    svc.store.chat_save(session["id"], session)
    loaded = svc.store.chat_get(session["id"])
    assert loaded is not None
    assert loaded["id"] == session["id"]
