"""Tests for context-window compaction."""

from app.gateway.base import Message, ToolCall
from app.harness.context import ContextManager


def test_no_compaction_when_under_budget():
    cm = ContextManager(char_budget=1000, keep_recent=2)
    msgs = [Message(role="user", content="hi"), Message(role="assistant", content="hello")]
    out, compacted = cm.fit(msgs)
    assert not compacted
    assert out == msgs


def test_compacts_old_large_contents_preserving_recent():
    cm = ContextManager(char_budget=100, keep_recent=1, min_cap=20)
    msgs = [
        Message(role="user", content="x" * 500),
        Message(role="assistant", content="y" * 500),
        Message(role="user", content="recent question"),
    ]
    out, compacted = cm.fit(msgs)
    assert compacted
    # last message kept verbatim
    assert out[-1].content == "recent question"
    # older ones shrunk
    assert len(out[0].content) < 500


def test_preserves_tool_call_pairing_fields():
    cm = ContextManager(char_budget=50, keep_recent=1, min_cap=10)
    msgs = [
        Message(role="assistant", content="a" * 200,
                tool_calls=[ToolCall("c1", "t", {})]),
        Message(role="tool", tool_call_id="c1", content="b" * 200),
        Message(role="user", content="next"),
    ]
    out, compacted = cm.fit(msgs)
    assert compacted
    assert out[0].tool_calls and out[0].tool_calls[0].id == "c1"
    assert out[1].tool_call_id == "c1"
