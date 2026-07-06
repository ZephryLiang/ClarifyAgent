"""Tests for trajectory-level replay (Evaluation)."""

import tempfile

import pytest

from app.evals import replay_run, trajectory_of
from app.harness import Tracer
from app.service import AppServices
from app.storage import Store

RESUME = "# 张三\n## 技能\nPython、Docker\n## 经历\n- 3 年经验"
JOB = "岗位\n任职要求:\n- Python\n- Kubernetes"


def test_trajectory_of_extracts_tool_order():
    trace = {"spans": [
        {"kind": "tool", "name": "tool:kb_grep", "start_ms": 20},
        {"kind": "llm", "name": "llm", "start_ms": 10},
        {"kind": "tool", "name": "tool:kb_read", "start_ms": 30},
    ]}
    assert trajectory_of(trace) == ["kb_grep", "kb_read"]


@pytest.mark.asyncio
async def test_replay_offline_matching_is_deterministic():
    services = AppServices(store=Store(tempfile.mktemp(suffix=".db")))
    tracer = Tracer()
    res = await services.matcher.run(RESUME, JOB, tracer)
    run_id = services.store.save_run(
        "matching", {"resume_text": RESUME, "job_text": JOB}, res.to_dict(), tracer.summary())

    replay = await replay_run(services, run_id)
    assert replay is not None
    assert replay.module == "matching"
    # offline => no tool spans => identical (empty) trajectories
    assert replay.trajectory_match
    # deterministic score => zero delta
    assert replay.diff["score"]["delta"] == 0.0


@pytest.mark.asyncio
async def test_replay_missing_run_returns_none():
    services = AppServices(store=Store(tempfile.mktemp(suffix=".db")))
    assert await replay_run(services, "nope") is None
