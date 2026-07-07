"""Tests for the agent harness: tool-calling loop, subagents, tracing."""

import pytest

from app.gateway.registry import Gateway
from app.harness import Agent, Orchestrator, ToolRegistry, Tracer
from app.harness.trace import SpanKind

from .fakes import EchoTool, FakeProvider, text_response, tool_response


@pytest.mark.asyncio
async def test_agent_executes_tool_then_answers():
    provider = FakeProvider("fake", [
        tool_response("echo", {"text": "hello"}),
        text_response("final answer"),
    ])
    gw = Gateway(providers=[provider])
    tools = ToolRegistry([EchoTool(transform=str.upper)])
    tracer = Tracer()
    agent = Agent(gw, tools, tracer, system="s", name="test-agent")

    result = await agent.run("do it")
    assert result.output == "final answer"
    assert result.tool_calls == 1
    # trace has an agent span, an llm span, and a tool span
    kinds = {s.kind for s in tracer.spans}
    assert SpanKind.AGENT in kinds and SpanKind.LLM in kinds and SpanKind.TOOL in kinds
    # the tool actually ran (uppercased)
    tool_span = next(s for s in tracer.spans if s.kind == SpanKind.TOOL)
    assert "HELLO" in str(tool_span.attributes.get("output"))


@pytest.mark.asyncio
async def test_agent_respects_max_iterations():
    # Always asks for a tool → never terminates on its own.
    provider = FakeProvider("fake", [tool_response("echo", {"text": "x"}) for _ in range(10)])
    gw = Gateway(providers=[provider])
    agent = Agent(gw, ToolRegistry([EchoTool()]), Tracer(), max_iterations=3)
    result = await agent.run("loop")
    assert result.stopped_reason == "max_iterations"
    assert result.iterations == 3


@pytest.mark.asyncio
async def test_orchestrator_runs_subagents_in_parallel():
    provider = FakeProvider("fake", [text_response(f"answer-{i}") for i in range(5)])
    gw = Gateway(providers=[provider])
    tracer = Tracer()
    orch = Orchestrator(gw, ToolRegistry(), tracer)
    from app.harness import SubagentTask

    tasks = [SubagentTask(name=f"t{i}", prompt="p", tool_names=[]) for i in range(3)]
    outcomes = await orch.run_parallel(tasks)
    assert len(outcomes) == 3
    assert all(o.ok for o in outcomes)
    assert any(s.kind == SpanKind.SUBAGENT for s in tracer.spans)


@pytest.mark.asyncio
async def test_unknown_tool_is_reported_not_raised():
    provider = FakeProvider("fake", [
        tool_response("does_not_exist", {}),
        text_response("done"),
    ])
    gw = Gateway(providers=[provider])
    agent = Agent(gw, ToolRegistry([EchoTool()]), Tracer())
    result = await agent.run("go")
    assert result.output == "done"
