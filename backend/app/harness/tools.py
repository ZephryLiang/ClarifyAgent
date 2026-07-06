"""Tool abstraction and registry for the agent harness.

A :class:`Tool` is the unit of capability the LLM can invoke. Built-in tools
(web search, knowledge-base grep/read, matching) and MCP-backed tools all
implement the same interface, so the agent loop treats them uniformly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..gateway.base import ToolSpec


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    data: Any = None


class Tool:
    """Base class for a callable tool.

    Subclasses set ``name``/``description``/``parameters`` and implement
    :meth:`run`. Tools may be sync or async; the harness awaits accordingly.
    """

    name: str = ""
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, parameters=self.parameters)

    async def run(self, **kwargs: Any) -> ToolResult:  # pragma: no cover - interface
        raise NotImplementedError


class FunctionTool(Tool):
    """Wrap a plain function as a tool (handy for quick/built-in tools)."""

    def __init__(self, name: str, description: str, parameters: dict[str, Any],
                 func: Callable[..., Any]) -> None:
        self.name = name
        self.description = description
        self.parameters = parameters
        self._func = func

    async def run(self, **kwargs: Any) -> ToolResult:
        import inspect

        result = self._func(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, ToolResult):
            return result
        return ToolResult(content=str(result), data=result)


class ToolRegistry:
    """A collection of tools available to an agent."""

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError("tool must have a name")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return [t.spec() for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def subset(self, names: list[str]) -> ToolRegistry:
        return ToolRegistry([self._tools[n] for n in names if n in self._tools])

    def __len__(self) -> int:
        return len(self._tools)
