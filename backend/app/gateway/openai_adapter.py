"""OpenAI-compatible provider adapter.

Works with OpenAI itself and any OpenAI-compatible endpoint (DeepSeek, Qwen /
DashScope compatible-mode, Moonshot, Zhipu, local gateways, ...).
"""

from __future__ import annotations

import json
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


class OpenAIAdapter(ChatProvider):
    protocol = "openai"

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
            from openai import OpenAI  # type: ignore
        except ImportError:
            return None
        kwargs: Dict[str, Any] = {"api_key": self.api_key, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        self._client = OpenAI(**kwargs)
        return self._client

    @staticmethod
    def _to_openai_messages(messages: List[Message], system: Optional[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if system:
            out.append({"role": "system", "content": system})
        for m in messages:
            if m.role == "assistant" and m.tool_calls:
                out.append({
                    "role": "assistant",
                    "content": m.content or None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                            },
                        }
                        for tc in m.tool_calls
                    ],
                })
            elif m.role == "tool":
                out.append({
                    "role": "tool",
                    "tool_call_id": m.tool_call_id,
                    "content": m.content,
                })
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    @staticmethod
    def _to_openai_tools(tools: Optional[List[ToolSpec]]) -> Optional[List[Dict[str, Any]]]:
        if not tools:
            return None
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]

    def chat(self, messages, tools=None, temperature=0.4, max_tokens=2048, system=None) -> ChatResponse:
        client = self._ensure_client()
        if client is None:
            raise ProviderError(f"provider '{self.name}' is not available (missing openai SDK or key)")

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": self._to_openai_messages(messages, system),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        oa_tools = self._to_openai_tools(tools)
        if oa_tools:
            kwargs["tools"] = oa_tools

        try:
            resp = client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - normalise to ProviderError
            raise ProviderError(str(exc)) from exc

        choice = resp.choices[0]
        msg = choice.message
        tool_calls: List[ToolCall] = []
        for tc in (getattr(msg, "tool_calls", None) or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append(ToolCall(id=tc.id or str(uuid.uuid4()), name=tc.function.name, arguments=args))

        usage = Usage()
        if getattr(resp, "usage", None):
            usage = Usage(
                prompt_tokens=resp.usage.prompt_tokens or 0,
                completion_tokens=resp.usage.completion_tokens or 0,
                total_tokens=resp.usage.total_tokens or 0,
            )

        return ChatResponse(
            content=msg.content or "",
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else (choice.finish_reason or "stop"),
            usage=usage,
            provider=self.name,
            model=self.model,
            raw=resp,
        )
