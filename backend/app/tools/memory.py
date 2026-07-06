"""Agentic memory tools: let an agent read and write long-term memory."""

from __future__ import annotations

from typing import Any

from ..harness.tools import Tool, ToolResult
from ..memory import MemoryManager


class MemorySearchTool(Tool):
    name = "memory_search"
    description = (
        "检索长期记忆（既往洞见、既定原则、用户偏好、反复出现的要点）。"
        "在给出建议前先查一下，保持与历史一致、避免重复劳动。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "检索关键词"},
            "kind": {"type": "string", "description": "可选类型: insight|principle|preference|fact|recurring"},
        },
        "required": ["query"],
    }

    def __init__(self, manager: MemoryManager) -> None:
        self._m = manager

    async def run(self, query: str, kind: str | None = None, **_: Any) -> ToolResult:  # type: ignore[override]
        items = self._m.search(query, kind)
        if not items:
            return ToolResult(content="（无相关记忆）", data=[])
        lines = ["相关记忆:"]
        for it in items:
            tag = f" #{','.join(it.tags)}" if it.tags else ""
            lines.append(f"- [{it.kind}] {it.content} (salience={it.salience}){tag}")
        return ToolResult(content="\n".join(lines), data=[it.to_dict() for it in items])


class MemoryWriteTool(Tool):
    name = "memory_write"
    description = (
        "把一条值得长期记住的洞见/原则/偏好写入记忆。"
        "只写真正可复用、跨会话有价值的内容；重复内容会自动合并并增强，无需担心重复。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "要记住的内容（简洁一句）"},
            "kind": {"type": "string", "description": "insight|principle|preference|fact|recurring"},
            "tags": {"type": "array", "items": {"type": "string"}, "description": "标签"},
        },
        "required": ["content"],
    }

    def __init__(self, manager: MemoryManager, source: str = "agent") -> None:
        self._m = manager
        self._source = source

    async def run(self, content: str, kind: str = "insight", tags=None, **_: Any) -> ToolResult:  # type: ignore[override]
        item = self._m.add(content, kind=kind, tags=list(tags or []), source=self._source)
        verb = "已合并强化" if item.salience > 1 else "已记录"
        return ToolResult(content=f"{verb}记忆: {item.content} (salience={item.salience})",
                          data=item.to_dict())


def build_memory_tools(manager: MemoryManager) -> list[Tool]:
    return [MemorySearchTool(manager), MemoryWriteTool(manager)]
