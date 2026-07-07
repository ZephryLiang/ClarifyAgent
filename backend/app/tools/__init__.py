"""Built-in agent tools and registry factory."""

from __future__ import annotations

from pathlib import Path

from ..harness.tools import Tool, ToolRegistry
from .builtins import SkillMatchTool
from .kb import KBGrepTool, KBListTool, KBReadTool, build_kb_tools
from .web_search import DuckDuckGoBackend, WebSearchTool

__all__ = [
    "WebSearchTool",
    "DuckDuckGoBackend",
    "KBListTool",
    "KBGrepTool",
    "KBReadTool",
    "build_kb_tools",
    "SkillMatchTool",
    "build_builtin_tools",
    "build_registry",
]


def build_builtin_tools(kb_root: Path | None = None) -> list[Tool]:
    """All dependency-light built-in tools."""

    tools: list[Tool] = [WebSearchTool(), SkillMatchTool()]
    tools.extend(build_kb_tools(kb_root))
    return tools


def build_registry(extra: list[Tool] | None = None, kb_root: Path | None = None) -> ToolRegistry:
    registry = ToolRegistry(build_builtin_tools(kb_root))
    for t in extra or []:
        registry.register(t)
    return registry
