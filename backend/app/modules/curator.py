"""MemoryCurator: reflect on a completed run and persist durable memories.

Runs after each feature module (best-effort, never fatal). With an LLM it asks a
lightweight agent to extract cross-session-useful insights; offline it derives
memories heuristically from structured results (e.g. recurring missing skills).
"""

from __future__ import annotations

from typing import Any

from ..gateway.registry import Gateway
from ..harness import Agent, ToolRegistry, Tracer
from ..harness.trace import SpanKind, SpanStatus
from ..memory import MemoryItem, MemoryManager
from .base import extract_json, llm_available

_SYSTEM = """你是记忆管理员。从本次求职任务的结果中，提炼 0-3 条**跨会话可复用**的长期记忆：
- insight（洞见）/ principle（原则）/ preference（用户偏好）/ recurring（反复出现的要点）。
- 只保留真正有长期价值、可指导未来的内容；琐碎、一次性的不要。
- 每条尽量简洁（一句话）。
只输出 JSON：{"memories": [{"content": "...", "kind": "insight", "tags": ["..."]}]}"""


class MemoryCurator:
    def __init__(self, manager: MemoryManager, gateway: Gateway | None = None) -> None:
        self.manager = manager
        self.gateway = gateway

    async def reflect(self, module: str, input_data: dict[str, Any], result: dict[str, Any],
                      tracer: Tracer | None = None) -> list[MemoryItem]:
        tracer = tracer or Tracer()
        span = tracer.start_span("memory-reflect", SpanKind.AGENT, module=module,
                                 has_llm=llm_available(self.gateway))
        try:
            if llm_available(self.gateway):
                items = await self._reflect_llm(module, result, tracer, span.id)
            else:
                items = self._reflect_offline(module, input_data, result)
            tracer.end_span(span, SpanStatus.OK, stored=len(items))
            return items
        except Exception as exc:  # noqa: BLE001 - reflection must never break a run
            tracer.end_span(span, SpanStatus.ERROR, error=str(exc))
            return []

    async def _reflect_llm(self, module: str, result: dict[str, Any],
                           tracer: Tracer, parent_id: str) -> list[MemoryItem]:
        assert self.gateway is not None
        import json

        agent = Agent(self.gateway, ToolRegistry(), tracer, system=_SYSTEM,
                      name="memory-curator", temperature=0.2, parent_span_id=parent_id)
        prompt = f"任务类型: {module}\n结果(JSON):\n{json.dumps(result, ensure_ascii=False)[:3000]}"
        out = await agent.run(prompt)
        data = extract_json(out.output) or {}
        stored: list[MemoryItem] = []
        for m in (data.get("memories", []) if isinstance(data, dict) else []):
            content = str(m.get("content", "")).strip()
            if not content:
                continue
            stored.append(self.manager.add(
                content, kind=str(m.get("kind", "insight")),
                tags=[str(t) for t in m.get("tags", [])], source=f"reflect:{module}"))
        return stored

    def _reflect_offline(self, module: str, input_data: dict[str, Any],
                         result: dict[str, Any]) -> list[MemoryItem]:
        stored: list[MemoryItem] = []
        if module == "matching":
            match = result.get("match") or {}
            for skill in (match.get("missing_required") or [])[:5]:
                stored.append(self.manager.add(
                    f"目标岗位常要求但简历尚缺: {skill}", kind="recurring",
                    tags=[skill, "skill-gap"], source="reflect:matching"))
        elif module == "retrospective":
            for w in (result.get("weaknesses") or [])[:3]:
                stored.append(self.manager.add(
                    f"面试待改进: {w}", kind="insight", tags=["interview"],
                    source="reflect:retrospective"))
        elif module == "resume_rewrite":
            for s in (result.get("suggestions") or []):
                for n in (s.get("needs_input") or [])[:1]:
                    stored.append(self.manager.add(
                        f"简历待补充: {n}", kind="recurring", tags=["resume"],
                        source="reflect:resume_rewrite"))
        return stored
