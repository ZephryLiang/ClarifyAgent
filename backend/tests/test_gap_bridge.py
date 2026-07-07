"""Tests for gap bridge: gap analysis, tech research scoring, project advisor."""

from __future__ import annotations

import pytest

from app.modules.gap_analyzer import GapAnalyzer
from app.modules.project_advisor import ProjectAdvisor
from app.modules.tech_research import TechResearchAgent, score_source, TechResearchDigest, ScoredSource


SAMPLE_JD = """
字节跳动 Agent Runtime 后端
任职要求：Go Python Kubernetes 分布式系统
"""

SAMPLE_RESUME = """
工作经历
技能：Python Redis MySQL
项目：订单系统
"""


@pytest.mark.asyncio
async def test_gap_analyzer_offline():
    result = await GapAnalyzer().run(SAMPLE_RESUME, SAMPLE_JD)
    assert result.score >= 0
    assert result.gaps
    assert not result.llm_used


def test_score_source_production_blog():
    score, signals = score_source(
        "Uber Engineering: Production Agent Runtime",
        "distributed production scale latency failure recovery",
        "blog",
    )
    assert score >= 55
    assert "production_pain" in signals or "authority" in signals


def test_score_source_penalizes_tutorial():
    score, signals = score_source(
        "Hello World Tutorial",
        "beginner hello world getting started tutorial",
        "blog",
    )
    assert score < 55
    assert "generic_tutorial" in signals


@pytest.mark.asyncio
async def test_project_advisor_from_offline_digest():
    digest = TechResearchDigest(
        theme="agent runtime",
        sources=[
            ScoredSource(
                title="Durable Execution",
                url="https://example.com",
                snippet="production checkpoint recovery at scale",
                source_type="blog",
                score=70,
                signals=["production_pain"],
            ),
        ],
        high_value_count=1,
    )
    proposal = await ProjectAdvisor().propose_from_research("agent runtime", digest)
    assert proposal.title
    assert proposal.mvp_scope
    assert proposal.warning


@pytest.mark.asyncio
async def test_tech_research_offline():
    digest = await TechResearchAgent().run("kubernetes")
    assert digest.theme == "kubernetes"
    assert digest.sources


def test_research_curator_persists_heuristic():
    from app.service import AppServices
    from app.modules.research_curator import ResearchCurator

    svc = AppServices()
    digest = TechResearchDigest(
        theme="redis",
        sources=[
            ScoredSource(
                title="Redis at scale",
                url="https://example.com/redis",
                snippet="production latency failure recovery",
                source_type="blog",
                score=72,
                signals=["production_pain"],
            ),
        ],
    )
    ids = ResearchCurator(svc.memory).curate(digest)
    assert ids
    items = svc.memory.list(kind="heuristic")
    assert any("redis" in i.content.lower() for i in items)
