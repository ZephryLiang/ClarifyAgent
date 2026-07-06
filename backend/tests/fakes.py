"""Test doubles: a scriptable fake LLM provider and a simple tool."""

from __future__ import annotations

from collections.abc import Callable

from app.gateway.base import ChatProvider, ChatResponse, Message, ToolCall, Usage
from app.harness.tools import Tool, ToolResult


class FakeProvider(ChatProvider):
    """A provider that replays a scripted list of responses."""

    def __init__(self, name: str, responses: list[ChatResponse], available: bool = True) -> None:
        self.name = name
        self.protocol = "fake"
        self.model = "fake-model"
        self._responses = list(responses)
        self._available = available
        self.calls: list[list[Message]] = []

    def available(self) -> bool:
        return self._available

    def chat(self, messages, tools=None, temperature=0.4, max_tokens=2048, system=None) -> ChatResponse:
        self.calls.append(list(messages))
        if not self._responses:
            return ChatResponse(content="(no more scripted responses)", provider=self.name)
        resp = self._responses.pop(0)
        resp.provider = self.name
        return resp


class FailingProvider(ChatProvider):
    """A provider that always raises to exercise fallback paths."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.protocol = "fake"
        self.model = "fake"

    def available(self) -> bool:
        return True

    def chat(self, *args, **kwargs):
        from app.gateway.base import ProviderError

        raise ProviderError(f"{self.name} always fails")


def text_response(content: str) -> ChatResponse:
    return ChatResponse(content=content, finish_reason="stop", usage=Usage(total_tokens=5))


def tool_response(tool_name: str, arguments: dict, call_id: str = "call_1") -> ChatResponse:
    return ChatResponse(
        content="",
        tool_calls=[ToolCall(id=call_id, name=tool_name, arguments=arguments)],
        finish_reason="tool_calls",
        usage=Usage(total_tokens=5),
    )


class EchoTool(Tool):
    name = "echo"
    description = "echo back the text"
    parameters = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}

    def __init__(self, transform: Callable[[str], str] | None = None) -> None:
        self._transform = transform or (lambda s: s)

    async def run(self, text: str = "") -> ToolResult:
        return ToolResult(content=self._transform(text))


class SideEffectTool(Tool):
    """A tool that records executions; used to test the governance gate."""

    name = "send_message"
    description = "send a message (side-effecting)"
    parameters = {"type": "object", "properties": {"to": {"type": "string"}}}
    side_effect = True

    def __init__(self) -> None:
        self.executed = 0

    async def run(self, **kwargs) -> ToolResult:
        self.executed += 1
        return ToolResult(content="sent")
