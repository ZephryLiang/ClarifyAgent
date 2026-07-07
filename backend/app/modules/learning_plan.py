"""Learning plan generator with time budget and tier priorities."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .base import load_kb_relative
from .requirement_synth import RequirementMatrix, RequirementSynthesizer


@dataclass
class LearningPhase:
    week: int
    focus: str
    hours: float
    topics: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "week": self.week,
            "focus": self.focus,
            "hours": self.hours,
            "topics": self.topics,
            "outputs": self.outputs,
        }


@dataclass
class LearningPlan:
    time_budget: dict[str, Any] = field(default_factory=dict)
    phases: list[LearningPhase] = field(default_factory=list)
    deferred: list[dict] = field(default_factory=list)
    rationale: str = ""
    truncated: bool = False

    def to_dict(self) -> dict:
        return {
            "time_budget": self.time_budget,
            "phases": [p.to_dict() for p in self.phases],
            "deferred": self.deferred,
            "rationale": self.rationale,
            "truncated": self.truncated,
        }


class LearningPlanGenerator:
    def __init__(self) -> None:
        self.synth = RequirementSynthesizer()
        self._rubric = load_kb_relative("learning", "priority_rubric.md")

    def apply_revision(self, matrix: RequirementMatrix, instruction: str) -> RequirementMatrix:
        text = instruction.lower()
        for row in matrix.rows:
            if row.topic.lower() in text:
                if any(k in text for k in ["最重要", "优先", "先学", "p0", "提前"]):
                    matrix.overrides[row.topic] = "P0"
                    row.effective_tier = "P0"
                    row.override_reason = "用户指定优先"
                if any(k in text for k in ["不要", "删掉", "defer", "暂缓"]):
                    matrix.overrides[row.topic] = "P3"
                    row.effective_tier = "P3"
        m = re.search(r"(\d+)\s*周", instruction)
        h = re.search(r"(\d+)\s*小时", instruction)
        if m or h:
            pass  # caller updates workspace time_budget via copilot
        return matrix

    def generate(
        self,
        matrix: RequirementMatrix,
        time_budget: dict[str, Any],
        resume_text: str = "",
    ) -> LearningPlan:
        weeks = int(time_budget.get("weeks") or 4)
        hpw = float(time_budget.get("hours_per_week") or 10)
        total = weeks * hpw
        p0 = [r for r in matrix.rows if r.effective_tier == "P0"]
        p1 = [r for r in matrix.rows if r.effective_tier == "P1"]
        p2 = [r for r in matrix.rows if r.effective_tier == "P2"]

        phases: list[LearningPhase] = []
        p0_hours = total * 0.6
        p1_hours = total * 0.3
        per_p0 = p0_hours / max(len(p0), 1)
        w = 1
        for row in p0[:weeks]:
            phases.append(LearningPhase(
                week=w,
                focus=f"P0: {row.topic}",
                hours=round(min(hpw, per_p0), 1),
                topics=[row.topic],
                outputs=[f"读懂 {row.topic} 生产场景", "MVP milestone"],
            ))
            w += 1
        if w <= weeks and p1:
            for row in p1[: max(0, weeks - w + 1)]:
                phases.append(LearningPhase(
                    week=w,
                    focus=f"P1: {row.topic}",
                    hours=round(min(hpw, p1_hours / max(len(p1), 1)), 1),
                    topics=[row.topic],
                    outputs=["深化实践"],
                ))
                w += 1

        deferred = [{"topic": r.topic, "tier": r.effective_tier, "reason": "时间有限"} for r in p2]
        truncated = len(p0) * hpw > total
        rationale = (
            f"共 {matrix.job_count} 份 JD；P0 占 ~60% 学时（{len(p0)} 主题）。"
            + (" 预算不足，建议延长周期。" if truncated else "")
        )
        if self._rubric:
            rationale += " 分级依据见 priority_rubric。"
        return LearningPlan(
            time_budget={"weeks": weeks, "hours_per_week": hpw, "total_hours": total},
            phases=phases,
            deferred=deferred,
            rationale=rationale,
            truncated=truncated,
        )
