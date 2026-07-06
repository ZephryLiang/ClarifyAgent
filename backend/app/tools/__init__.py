"""Built-in agent tools and registry factory."""

from pathlib import Path
from typing import List, Optional

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


def build_builtin_tools(kb_root: Optional[Path] = None) -> List[Tool]:
    """All dependency-light built-in tools."""

    tools: List[Tool] = [WebSearchTool(), SkillMatchTool()]
    tools.extend(build_kb_tools(kb_root))
    return tools


def build_registry(extra: Optional[List[Tool]] = None, kb_root: Optional[Path] = None) -> ToolRegistry:
    registry = ToolRegistry(build_builtin_tools(kb_root))
    for t in extra or []:
        registry.register(t)
    return registry
