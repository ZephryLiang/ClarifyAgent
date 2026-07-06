"""Durable execution: checkpoint & resume the agent loop (Lifecycle layer).

The agent persists its conversation state after each iteration. If the process
crashes or a long task is interrupted, a new :class:`Agent` with the same
``checkpoint_id`` resumes from the last saved step instead of starting over.

Messages (including tool-call linkage) are serialized to plain dicts so they
survive a JSON round-trip.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..gateway.base import Message, ToolCall


def serialize_messages(messages: list[Message]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in messages:
        out.append({
            "role": m.role,
            "content": m.content,
            "tool_calls": [{"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                           for tc in m.tool_calls],
            "tool_call_id": m.tool_call_id,
            "name": m.name,
        })
    return out


def deserialize_messages(data: list[dict[str, Any]]) -> list[Message]:
    out: list[Message] = []
    for d in data:
        out.append(Message(
            role=d["role"],
            content=d.get("content", ""),
            tool_calls=[ToolCall(id=tc["id"], name=tc["name"], arguments=tc.get("arguments", {}))
                        for tc in d.get("tool_calls", [])],
            tool_call_id=d.get("tool_call_id"),
            name=d.get("name"),
        ))
    return out


class Checkpointer(Protocol):
    def save(self, cp_id: str, state: dict[str, Any], done: bool = False) -> None: ...
    def load(self, cp_id: str) -> dict[str, Any] | None: ...
    def delete(self, cp_id: str) -> bool: ...


class StoreCheckpointer:
    """Checkpointer backed by the SQLite :class:`Store`."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def save(self, cp_id: str, state: dict[str, Any], done: bool = False) -> None:
        self.store.checkpoint_save(cp_id, state, done)

    def load(self, cp_id: str) -> dict[str, Any] | None:
        return self.store.checkpoint_load(cp_id)

    def delete(self, cp_id: str) -> bool:
        return self.store.checkpoint_delete(cp_id)


class MemoryCheckpointer:
    """In-memory checkpointer (handy for tests)."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def save(self, cp_id: str, state: dict[str, Any], done: bool = False) -> None:
        self._data[cp_id] = {"done": done, "state": state}

    def load(self, cp_id: str) -> dict[str, Any] | None:
        return self._data.get(cp_id)

    def delete(self, cp_id: str) -> bool:
        return self._data.pop(cp_id, None) is not None
