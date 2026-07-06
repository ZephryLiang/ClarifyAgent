"""Tests for durable execution: checkpoint & resume (Lifecycle)."""

import pytest

from app.gateway.base import Message, ToolCall
from app.gateway.registry import Gateway
from app.harness import Agent, MemoryCheckpointer, ToolRegistry, Tracer
from app.harness.checkpoint import deserialize_messages, serialize_messages

from .fakes import EchoTool, FakeProvider, text_response, tool_response


def test_message_serialization_roundtrip():
    msgs = [
        Message(role="user", content="hi"),
        Message(role="assistant", content="", tool_calls=[ToolCall("c1", "echo", {"text": "x"})]),
        Message(role="tool", tool_call_id="c1", content="x"),
    ]
    restored = deserialize_messages(serialize_messages(msgs))
    assert restored[1].tool_calls[0].id == "c1"
    assert restored[2].tool_call_id == "c1"


@pytest.mark.asyncio
async def test_checkpoint_saved_on_interruption():
    cp = MemoryCheckpointer()
    provider = FakeProvider("fake", [tool_response("echo", {"text": "x"}) for _ in range(5)])
    agent = Agent(Gateway(providers=[provider]), ToolRegistry([EchoTool()]), Tracer(),
                  max_iterations=1, checkpointer=cp, checkpoint_id="cp1")
    result = await agent.run("start")
    assert result.stopped_reason == "max_iterations"
    saved = cp.load("cp1")
    assert saved is not None and not saved["done"]
    assert saved["state"]["iteration"] == 1


@pytest.mark.asyncio
async def test_resume_continues_from_checkpoint():
    cp = MemoryCheckpointer()
    # First agent: one tool iteration then interrupted by the budget.
    a1 = Agent(Gateway(providers=[FakeProvider("f", [tool_response("echo", {"text": "x"})])]),
               ToolRegistry([EchoTool()]), Tracer(),
               max_iterations=1, checkpointer=cp, checkpoint_id="cp2")
    await a1.run("start")
    saved_len = len(cp.load("cp2")["state"]["messages"])

    # Second agent resumes with the same id and finishes.
    a2 = Agent(Gateway(providers=[FakeProvider("f", [text_response("final")])]),
               ToolRegistry([EchoTool()]), Tracer(),
               max_iterations=5, checkpointer=cp, checkpoint_id="cp2")
    result = await a2.run("ignored-because-resumed")
    assert result.output == "final"
    # Resumed run started from restored history (>= what was saved).
    assert len(result.messages) >= saved_len
    assert cp.load("cp2")["done"]
