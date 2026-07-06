"""Tests for the verification closed loop and LLM-as-judge (offline)."""

import pytest

from app.modules.grounding import repair, verify_faithfulness
from app.modules.resume_rewrite import ResumeRewriter
from app.modules.verify import Judge


def test_repair_neutralises_unsupported_numbers():
    original = "负责订单系统重构"
    rewritten = "将延迟从 800ms 降到 200ms"
    report = verify_faithfulness(original, rewritten)
    assert not report.ok
    fixed = repair(rewritten, report)
    # after repair, re-verification passes (numbers placeholdered)
    assert verify_faithfulness(original, fixed).ok
    assert "待核实" in fixed


@pytest.mark.asyncio
async def test_rewrite_autorepairs_flagged_suggestions():
    # offline rewriter never fabricates, so inject via a crafted resume where the
    # heuristic keeps original numbers; then assert the loop leaves faithful output
    resume = "# 张三\n## 工作经历\n- 负责订单系统重构，QPS 从 2k 提升到 15k"
    result = await ResumeRewriter().run(resume)
    for s in result.suggestions:
        assert s.faithfulness is not None and s.faithfulness.ok


@pytest.mark.asyncio
async def test_judge_offline_scores_and_reasons():
    judge = Judge(gateway=None)
    good = await judge.score("将 QPS 从 2k 提升到 15k，P99 下降 40%。\n- 结构化\n- 有量化")
    poor = await judge.score("还行")
    assert good.score >= poor.score
    assert good.dimensions and not good.llm_used
