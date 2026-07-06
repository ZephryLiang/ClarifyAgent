"""Tests for the gateway adapters and registry routing/fallback."""

from app.gateway.anthropic_adapter import AnthropicAdapter
from app.gateway.base import Message, ToolCall, ToolSpec
from app.gateway.openai_adapter import OpenAIAdapter
from app.gateway.registry import Gateway

from .fakes import FailingProvider, FakeProvider, text_response


def test_openai_message_translation_roundtrip():
    adapter = OpenAIAdapter("openai", "gpt", api_key=None)
    messages = [
        Message(role="user", content="hi"),
        Message(role="assistant", content="", tool_calls=[ToolCall("c1", "search", {"q": "x"})]),
        Message(role="tool", tool_call_id="c1", content="result"),
    ]
    out = adapter._to_openai_messages(messages, system="sys")
    assert out[0] == {"role": "system", "content": "sys"}
    assert out[2]["tool_calls"][0]["function"]["name"] == "search"
    assert out[3]["role"] == "tool" and out[3]["tool_call_id"] == "c1"


def test_anthropic_translation_groups_tool_results_and_lifts_system():
    adapter = AnthropicAdapter("anthropic", "claude", api_key=None)
    messages = [
        Message(role="system", content="be nice"),
        Message(role="user", content="hi"),
        Message(role="assistant", content="", tool_calls=[ToolCall("c1", "t", {})]),
        Message(role="tool", tool_call_id="c1", content="r"),
    ]
    an_messages = adapter._to_anthropic_messages(messages)
    # system is not part of the message list
    assert all(m["role"] != "system" for m in an_messages)
    # tool result becomes a user turn with a tool_result block
    last = an_messages[-1]
    assert last["role"] == "user"
    assert last["content"][0]["type"] == "tool_result"
    assert adapter._collect_system(messages, None) == "be nice"


def test_anthropic_tool_spec_uses_input_schema():
    adapter = AnthropicAdapter("anthropic", "claude", api_key=None)
    tools = [ToolSpec(name="t", description="d", parameters={"type": "object", "properties": {}})]
    out = adapter._to_anthropic_tools(tools)
    assert out[0]["input_schema"] == {"type": "object", "properties": {}}


def test_gateway_prefers_named_provider():
    a = FakeProvider("a", [text_response("from-a")])
    b = FakeProvider("b", [text_response("from-b")])
    gw = Gateway(providers=[a, b])
    resp = gw.chat([Message(role="user", content="hi")], prefer="b")
    assert resp.content == "from-b"


def test_gateway_falls_back_on_failure():
    failing = FailingProvider("bad")
    good = FakeProvider("good", [text_response("recovered")])
    gw = Gateway(providers=[failing, good], max_retries=0)
    attempts = []
    resp = gw.chat([Message(role="user", content="hi")],
                   on_attempt=lambda name, err: attempts.append((name, err is not None)))
    assert resp.content == "recovered"
    assert ("bad", True) in attempts
    assert ("good", False) in attempts
