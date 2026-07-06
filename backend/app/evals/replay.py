"""Trajectory-level replay (Evaluation layer).

Re-executes a previously recorded run from its stored input, then compares the
new *trajectory* (the ordered sequence of tool calls) and the result against the
original. This powers regression checks: deterministic (offline) modules should
reproduce identical trajectories; with an LLM you can measure drift.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..harness import Tracer


def trajectory_of(trace: dict[str, Any]) -> list[str]:
    """Ordered list of tool names invoked in a trace (the trajectory)."""

    spans = [s for s in (trace or {}).get("spans", []) if s.get("kind") == "tool"]
    spans.sort(key=lambda s: s.get("start_ms", 0))
    return [s["name"].replace("tool:", "") for s in spans]


def _span_kind_counts(trace: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in (trace or {}).get("spans", []):
        counts[s["kind"]] = counts.get(s["kind"], 0) + 1
    return counts


@dataclass
class ReplayResult:
    run_id: str = ""
    module: str = ""
    original_trajectory: list[str] = field(default_factory=list)
    replayed_trajectory: list[str] = field(default_factory=list)
    trajectory_match: bool = False
    original_result: Any = None
    replayed_result: Any = None
    diff: dict[str, Any] = field(default_factory=dict)
    replayed_trace: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "module": self.module,
            "original_trajectory": self.original_trajectory,
            "replayed_trajectory": self.replayed_trajectory,
            "trajectory_match": self.trajectory_match,
            "diff": self.diff,
            "replayed_trace": self.replayed_trace,
        }


async def _rerun(services: Any, module: str, inp: dict[str, Any], tracer: Tracer) -> Any:
    inp = inp or {}
    if module == "resume_rewrite":
        return await services.rewriter.run(inp.get("resume_text", ""), inp.get("job_text"), tracer)
    if module == "matching":
        return await services.matcher.run(inp.get("resume_text", ""), inp.get("job_text", ""), tracer)
    if module == "outreach":
        return await services.outreach.run(inp.get("resume_text", ""), inp.get("job_text", ""),
                                           inp.get("style", "professional"), tracer)
    if module == "retrospective":
        return await services.retrospective.run(inp.get("transcript", ""), inp.get("job_text", ""),
                                                inp.get("company", ""), tracer)
    if module == "journal":
        return await services.journal.run(tracer)
    raise ValueError(f"module '{module}' 不支持回放")


def _result_diff(module: str, original: Any, replayed: Any) -> dict[str, Any]:
    """Compute a compact, module-aware diff between two results."""

    diff: dict[str, Any] = {}
    o = original or {}
    r = replayed or {}
    if module == "matching":
        os_ = (o.get("match") or {}).get("score")
        rs = (r.get("match") or {}).get("score")
        diff["score"] = {"original": os_, "replayed": rs,
                         "delta": None if (os_ is None or rs is None) else round(rs - os_, 1)}
    elif module == "resume_rewrite":
        diff["suggestion_count"] = {"original": len(o.get("suggestions", [])),
                                    "replayed": len(r.get("suggestions", []))}
    elif module == "outreach":
        diff["message_changed"] = o.get("message") != r.get("message")
    diff["llm_used"] = {"original": o.get("llm_used"), "replayed": r.get("llm_used")}
    return diff


async def replay_run(services: Any, run_id: str) -> ReplayResult | None:
    run = services.store.get_run(run_id)
    if not run:
        return None
    module = run["module"]
    original_result = run.get("result")
    original_trace = run.get("trace") or {}

    tracer = Tracer()
    replayed = await _rerun(services, module, run.get("input") or {}, tracer)
    replayed_result = replayed.to_dict() if hasattr(replayed, "to_dict") else replayed
    replayed_trace = tracer.summary()

    orig_traj = trajectory_of(original_trace)
    new_traj = trajectory_of(replayed_trace)

    diff = _result_diff(module, original_result, replayed_result)
    diff["span_kinds"] = {"original": _span_kind_counts(original_trace),
                          "replayed": _span_kind_counts(replayed_trace)}

    return ReplayResult(
        run_id=run_id, module=module,
        original_trajectory=orig_traj, replayed_trajectory=new_traj,
        trajectory_match=(orig_traj == new_traj),
        original_result=original_result, replayed_result=replayed_result,
        diff=diff, replayed_trace=replayed_trace,
    )
