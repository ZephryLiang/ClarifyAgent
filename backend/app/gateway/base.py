"""Provider-agnostic chat types.

The gateway normalises the differences between OpenAI's and Anthropic's APIs so
the agent harness can speak a single dialect regardless of the backing model.
Tool-calling in particular differs between the two vendors and is unified here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolSpec:
    """A tool the model may call. JSON-schema for parameters."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})


@dataclass
class ToolCall:
    """A model's request to invoke a tool."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class Message:
    """A unified chat message.

    ``role`` is one of ``system`` | ``user`` | ``assistant`` | ``tool``.
    For a ``tool`` message, ``tool_call_id`` links back to the originating call.
    An ``assistant`` message may carry ``tool_calls``.
    """

    role: str
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ChatResponse:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"  # "stop" | "tool_calls" | "length" | "error"
    usage: Usage = field(default_factory=Usage)
    provider: str = ""
    model: str = ""
    raw: Any = None

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class ChatProvider:
    """Abstract chat provider. Adapters implement :meth:`chat`."""

    name: str = "base"
    protocol: str = "base"
    model: str = ""

    def available(self) -> bool:  # pragma: no cover - trivial
        raise NotImplementedError

    def chat(
        self,
        messages: list[Message],
        tools: list[ToolSpec] | None = None,
        temperature: float = 0.4,
        max_tokens: int = 2048,
        system: str | None = None,
    ) -> ChatResponse:  # pragma: no cover - interface
        raise NotImplementedError


class ProviderError(RuntimeError):
    """Raised when a provider call fails (transport/auth/model)."""
