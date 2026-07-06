"""Tests for built-in tools (KB agentic search, skill match)."""

import pytest

from app.tools.builtins import SkillMatchTool
from app.tools.kb import KBGrepTool, KBListTool, KBReadTool


@pytest.mark.asyncio
async def test_kb_list_returns_documents():
    result = await KBListTool().run()
    assert "resume/" in result.content
    assert isinstance(result.data, list) and result.data


@pytest.mark.asyncio
async def test_kb_grep_finds_and_cites_lines():
    result = await KBGrepTool().run(pattern="STAR")
    assert result.data
    first = result.data[0]
    assert "path" in first and "line" in first


@pytest.mark.asyncio
async def test_kb_read_rejects_path_traversal():
    result = await KBReadTool().run(path="../../etc/passwd")
    assert result.is_error


@pytest.mark.asyncio
async def test_kb_read_returns_numbered_content():
    result = await KBReadTool().run(path="resume/xyz_formula.md")
    assert not result.is_error
    assert "XYZ" in result.content


@pytest.mark.asyncio
async def test_skill_match_tool_outputs_json():
    result = await SkillMatchTool().run(
        resume_text="技能 Python Docker", job_text="任职要求: Python Kubernetes"
    )
    assert "score" in result.content
    assert result.data is not None
