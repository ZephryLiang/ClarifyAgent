"""LLM-as-judge verification.

Scores an arbitrary artifact (cover letter, outreach message, rewritten bullet,
answer) against criteria. With an LLM it uses a judge prompt returning a
structured verdict; offline it falls back to transparent heuristics so the
verification surface is always available.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from .base import extract_json, llm_available

_SYSTEM = """你是严格但公正的评审。针对给定文本与评审维度打分。
输出 JSON：{"score": 0-100 整数, "passed": true/false, "rationale": "简述",
"dimensions": [{"name": "维度", "score": 0-100, "comment": "..."}]}"""

_DEFAULT_CRITERIA = ["相关性", "具体性/量化", "真诚度", "清晰度"]


@dataclass
class JudgeResult:
    score: int = 0
    passed: bool = False
    rationale: str = ""
    dimensions: list = field(default_factory=list)
    llm_used: bool = False

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "passed": self.passed,
            "rationale": self.rationale,
            "dimensions": self.dimensions,
            "llm_used": self.llm_used,
        }


class Judge:
    def __init__(self, gateway: Gateway | None = None) -> None:
        self.gateway = gateway

    async def score(self, content: str, criteria: list | None = None,
                    artifact_type: str = "文本", tracer: Tracer | None = None) -> JudgeResult:
        tracer = tracer or Tracer()
        criteria = criteria or _DEFAULT_CRITERIA
        span = tracer.start_span("judge", SpanKind.RETRIEVAL, has_llm=llm_available(self.gateway))
        try:
            if llm_available(self.gateway):
                result = await self._judge_llm(content, criteria, artifact_type, tracer, span.id)
            else:
                result = self._judge_offline(content, criteria)
            tracer.end_span(span, SpanStatus.OK, score=result.score)
            return result
        except Exception as exc:  # noqa: BLE001
            tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
            raise

    async def _judge_llm(self, content: str, criteria: list, artifact_type: str,
                         tracer: Tracer, parent_id: str) -> JudgeResult:
        assert self.gateway is not None
        agent = Agent(self.gateway, ToolRegistry(), tracer, system=_SYSTEM,
                      name="judge", temperature=0.1, parent_span_id=parent_id)
        prompt = (f"待评审类型：{artifact_type}\n评审维度：{'、'.join(criteria)}\n\n"
                  f"文本：\n{content}")
        out = await agent.run(prompt)
        data = extract_json(out.output) or {}
        if not isinstance(data, dict) or "score" not in data:
            return self._judge_offline(content, criteria)
        try:
            score = int(data.get("score", 0))
        except (TypeError, ValueError):
            score = 0
        return JudgeResult(
            score=score, passed=bool(data.get("passed", score >= 60)),
            rationale=str(data.get("rationale", "")),
            dimensions=[d for d in data.get("dimensions", []) if isinstance(d, dict)],
            llm_used=True,
        )

    @staticmethod
    def _judge_offline(content: str, criteria: list) -> JudgeResult:
        text = content.strip()
        length = len(text)
        has_number = bool(re.search(r"\d", text))
        has_structure = any(ch in text for ch in ("\n", "-", "•", "。"))
        score = 40
        dims = []
        rel = 60 if length > 40 else 35
        spec = 80 if has_number else 45
        clar = 70 if has_structure else 50
        score = int((rel + spec + clar) / 3)
        dims = [
            {"name": "相关性", "score": rel, "comment": "基于长度的启发式估计"},
            {"name": "具体性/量化", "score": spec, "comment": "含数字更佳" if has_number else "缺少量化"},
            {"name": "清晰度", "score": clar, "comment": "结构化更佳"},
        ]
        return JudgeResult(
            score=score, passed=score >= 60,
            rationale="离线启发式评分（未启用大模型）：基于长度、量化与结构。",
            dimensions=dims, llm_used=False,
        )
