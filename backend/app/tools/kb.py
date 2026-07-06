"""Agentic knowledge-base search tools ("LLM + grep" over a file corpus).

Instead of a vector store, the resume best-practice corpus is a small set of
Markdown files. The agent explores it with three tools — ``kb_list``,
``kb_grep``, ``kb_read`` — reading full documents and citing them precisely by
``file:line``. This keeps grounding lossless and citations verifiable, and adds
no embedding infrastructure.

All file access is confined to the knowledge-base root to prevent traversal.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from ..config import KNOWLEDGE_BASE_DIR
from ..harness.tools import Tool, ToolResult


def _safe_path(root: Path, rel: str) -> Path | None:
    """Resolve ``rel`` under ``root``; return None if it escapes the root."""

    candidate = (root / rel).resolve()
    root_resolved = root.resolve()
    if root_resolved == candidate or root_resolved in candidate.parents:
        return candidate
    return None


def _iter_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix in {".md", ".txt"})


class KBListTool(Tool):
    name = "kb_list"
    description = "列出简历最佳实践知识库中的所有文档（文件名 + 首行标题）。先用它了解有哪些依据可查。"
    parameters: Dict[str, Any] = {"type": "object", "properties": {}}

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or KNOWLEDGE_BASE_DIR

    async def run(self, **_: Any) -> ToolResult:
        files = _iter_files(self.root)
        if not files:
            return ToolResult(content="知识库为空。", data=[])
        lines = ["知识库文档:"]
        listing: List[Dict[str, str]] = []
        for f in files:
            rel = f.relative_to(self.root).as_posix()
            title = ""
            try:
                first = f.read_text(encoding="utf-8").splitlines()
                title = next((ln.lstrip("# ").strip() for ln in first if ln.strip()), "")
            except OSError:
                pass
            lines.append(f"- {rel} — {title}")
            listing.append({"path": rel, "title": title})
        return ToolResult(content="\n".join(lines), data=listing)


class KBGrepTool(Tool):
    name = "kb_grep"
    description = (
        "在简历最佳实践知识库中按关键词/正则搜索，返回匹配的『文件:行号: 内容』。"
        "用于快速定位相关依据（如 'quantify'、'STAR'、'action verb'、'量化'）。"
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "搜索关键词或正则表达式"},
            "max_results": {"type": "integer", "description": "最多返回匹配行数 (默认 20)", "default": 20},
        },
        "required": ["pattern"],
    }

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or KNOWLEDGE_BASE_DIR

    async def run(self, pattern: str, max_results: int = 20) -> ToolResult:
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        matches: List[Dict[str, Any]] = []
        for f in _iter_files(self.root):
            rel = f.relative_to(self.root).as_posix()
            try:
                for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                    if regex.search(line):
                        matches.append({"path": rel, "line": i, "text": line.strip()})
                        if len(matches) >= max_results:
                            break
            except OSError:
                continue
            if len(matches) >= max_results:
                break

        if not matches:
            return ToolResult(content=f"未在知识库中找到匹配 '{pattern}' 的内容。", data=[])
        lines = [f"匹配 '{pattern}':"]
        for m in matches:
            lines.append(f"{m['path']}:{m['line']}: {m['text']}")
        return ToolResult(content="\n".join(lines), data=matches)


class KBReadTool(Tool):
    name = "kb_read"
    description = (
        "读取知识库中某个文档的完整内容（带行号），用于获取可引用的最佳实践原文。"
        "引用时请注明『文件:行号』。"
    )
    parameters: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "kb_list 返回的文档相对路径"},
        },
        "required": ["path"],
    }

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or KNOWLEDGE_BASE_DIR

    async def run(self, path: str) -> ToolResult:
        target = _safe_path(self.root, path)
        if target is None or not target.is_file():
            return ToolResult(content=f"文档不存在或路径非法: {path}", is_error=True)
        try:
            content = target.read_text(encoding="utf-8")
        except OSError as exc:
            return ToolResult(content=f"读取失败: {exc}", is_error=True)
        numbered = "\n".join(f"{i:>4}| {ln}" for i, ln in enumerate(content.splitlines(), 1))
        return ToolResult(content=f"# {path}\n{numbered}", data={"path": path, "content": content})


def build_kb_tools(root: Path | None = None) -> List[Tool]:
    return [KBListTool(root), KBGrepTool(root), KBReadTool(root)]
