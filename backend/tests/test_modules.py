"""Tests for feature modules in offline mode (no LLM configured)."""

import pytest

from app.modules import (
    Matcher,
    MockInterviewer,
    OutreachWriter,
    ResumeRewriter,
    Retrospective,
)

RESUME = """# 张三
后端工程师
## 技能
Python、Docker、Kubernetes
## 工作经历
- 负责订单系统重构
- 主导支付网关微服务拆分
"""

JOB = """高级后端工程师
任职要求:
- 精通 Python
- 熟悉 Kubernetes
- 5 年经验
加分项:
- Kafka
"""


@pytest.mark.asyncio
async def test_resume_rewrite_offline_cites_and_verifies():
    result = await ResumeRewriter().run(RESUME)
    assert not result.llm_used
    assert result.suggestions
    # every suggestion carries a faithfulness report and at least one citation
    for s in result.suggestions:
        assert s.faithfulness is not None
        assert s.principles


@pytest.mark.asyncio
async def test_matcher_offline_returns_score():
    report = await Matcher().run(RESUME, JOB)
    assert report.match is not None
    assert report.match.score > 0
    assert not report.llm_used


@pytest.mark.asyncio
async def test_outreach_offline_message_mentions_role():
    result = await OutreachWriter().run(RESUME, JOB)
    assert result.message
    assert not result.llm_used


@pytest.mark.asyncio
async def test_interview_offline_flow_progresses():
    iv = MockInterviewer()
    session = iv.create(RESUME, JOB, max_questions=3)
    q1 = await iv.ask_next(session)
    assert q1
    iv.answer(session, "我做过订单系统重构，QPS 提升 7 倍")
    q2 = await iv.ask_next(session)
    assert q2 != q1
    assert session.question_count == 2


@pytest.mark.asyncio
async def test_retrospective_offline_produces_plan():
    transcript = "面试官: 自我介绍\n候选人: 我有 5 年经验，QPS 提升 7 倍"
    result = await Retrospective().run(transcript)
    assert result.improvement_plan
    assert not result.llm_used
