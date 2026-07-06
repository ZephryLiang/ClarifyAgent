"""Anthropic (Claude) native provider adapter.

Anthropic's Messages API differs from OpenAI in three ways we must normalise:

* the ``system`` prompt is a top-level parameter, not a message;
* tool calls appear as ``tool_use`` content blocks on the assistant turn;
* tool results are sent back as ``tool_result`` blocks inside a *user* message.

This adapter translates our unified :class:`Message` list into that shape and
maps the response back into a provider-agnostic :class:`ChatResponse`.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from .base import (
    ChatProvider,
    ChatResponse,
    Message,
    ProviderError,
    ToolCall,
    ToolSpec,
    Usage,
)


class AnthropicAdapter(ChatProvider):
    protocol = "anthropic"

    def __init__(self, name: str, model: str, api_key: Optional[str],
                 base_url: Optional[str] = None, timeout: float = 60.0) -> None:
        self.name = name
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self._client = None

    def available(self) -> bool:
        return bool(self.api_key) and self._ensure_client() is not None

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            return None
        try:
            from anthropic import Anthropic  # type: ignore
        except ImportError:
            return None
        kwargs: Dict[str, Any] = {"api_key": self.api_key, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = Anthropic(**kwargs)
        return self._client

    @staticmethod
    def _to_anthropic_messages(messages: List[Message]) -> List[Dict[str, Any]]:
        """Translate unified messages into Anthropic message blocks.

        Consecutive ``tool`` results are merged into a single user turn, as the
        API expects tool_result blocks grouped in one user message.
        """

        out: List[Dict[str, Any]] = []
        pending_tool_results: List[Dict[str, Any]] = []

        def flush_tool_results() -> None:
            nonlocal pending_tool_results
            if pending_tool_results:
                out.append({"role": "user", "content": pending_tool_results})
                pending_tool_results = []

        for m in messages:
            if m.role == "system":
                continue  # handled separately as top-level system
            if m.role == "tool":
                pending_tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": m.tool_call_id,
                    "content": m.content,
                })
                continue

            flush_tool_results()

            if m.role == "assistant" and m.tool_calls:
                blocks: List[Dict[str, Any]] = []
                if m.content:
                    blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.arguments,
                    })
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": m.role, "content": m.content})

        flush_tool_results()
        return out

    @staticmethod
    def _collect_system(messages: List[Message], system: Optional[str]) -> Optional[str]:
        parts: List[str] = []
        if system:
            parts.append(system)
        for m in messages:
            if m.role == "system" and m.content:
                parts.append(m.content)
        return "\n\n".join(parts) if parts else None

    @staticmethod
    def _to_anthropic_tools(tools: Optional[List[ToolSpec]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None
        return [
            {"name": t.name, "description": t.description, "input_schema": t.parameters}
            for t in tools
        ]

    def chat(self, messages, tools=None, temperature=0.4, max_tokens=2048, system=None) -> ChatResponse:
        client = self._ensure_client()
        if client is None:
            raise ProviderError(f"provider '{self.name}' is not available (missing anthropic SDK or key)")

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": self._to_anthropic_messages(messages),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        sys_prompt = self._collect_system(messages, system)
        if sys_prompt:
            kwargs["system"] = sys_prompt
        an_tools = self._to_anthropic_tools(tools)
        if an_tools:
            kwargs["tools"] = an_tools

        try:
            resp = client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - normalise
            raise ProviderError(str(exc)) from exc

        text_parts: List[str] = []
        tool_calls: List[ToolCall] = []
        for block in resp.content:
            btype = getattr(block, "type", None)
            if btype == "text":
                text_parts.append(block.text)
            elif btype == "tool_use":
                tool_calls.append(ToolCall(
                    id=getattr(block, "id", None) or str(uuid.uuid4()),
                    name=block.name,
                    arguments=dict(block.input or {}),
                ))

        usage = Usage()
        if getattr(resp, "usage", None):
            usage = Usage(
                prompt_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
                completion_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
            )
            usage.total_tokens = usage.prompt_tokens + usage.completion_tokens

        return ChatResponse(
            content="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else (getattr(resp, "stop_reason", None) or "stop"),
            usage=usage,
            provider=self.name,
            model=self.model,
            raw=resp,
        )
