"""Web search tool backed by DuckDuckGo (no API key required).

Uses the ``ddgs`` package when installed. If it is unavailable or the network
call fails, the tool returns a clear, non-fatal message so the agent can carry
on rather than crashing. The design is pluggable: swapping in Tavily/Serper/
Brave later means adding another ``SearchBackend`` and selecting it via config.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ..harness.tools import Tool, ToolResult


class WebSearchBackend:
    def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:  # pragma: no cover
        raise NotImplementedError


class DuckDuckGoBackend(WebSearchBackend):
    def available(self) -> bool:
        try:
            import ddgs  # type: ignore  # noqa: F401
            return True
        except ImportError:
            try:
                import duckduckgo_search  # type: ignore  # noqa: F401
                return True
            except ImportError:
                return False

    def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        results: list[dict[str, str]] = []
        ddgs_cls = None
        try:
            from ddgs import DDGS  # type: ignore
            ddgs_cls = DDGS
        except ImportError:
            try:
                from duckduckgo_search import DDGS  # type: ignore
                ddgs_cls = DDGS
            except ImportError:
                return results
        with ddgs_cls() as ddgs:
            for item in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("href", item.get("url", "")),
                    "snippet": item.get("body", item.get("snippet", "")),
                })
        return results


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "在互联网上搜索信息（公司背景、行业动态、真实面经、职位信息等）。"
        "返回标题、链接和摘要。用于需要外部实时信息的场景。"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词/查询语句"},
            "max_results": {"type": "integer", "description": "返回结果数量 (默认 5)", "default": 5},
        },
        "required": ["query"],
    }

    def __init__(self, backend: WebSearchBackend | None = None) -> None:
        self.backend = backend or DuckDuckGoBackend()

    async def run(self, query: str, max_results: int = 5, **_: Any) -> ToolResult:  # type: ignore[override]
        loop = asyncio.get_event_loop()
        try:
            results = await loop.run_in_executor(
                None, lambda: self.backend.search(query, max_results)
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(content=f"网络搜索暂不可用: {exc}", is_error=True)

        if not results:
            return ToolResult(
                content=(
                    f"未找到 '{query}' 的搜索结果，或搜索后端未安装 (pip install ddgs)。"
                ),
                data=[],
            )

        lines = [f"搜索 '{query}' 的结果:"]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
        return ToolResult(content="\n".join(lines), data=results)
