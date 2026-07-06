"""Context-window management: keep conversation history within a budget.

Long agent loops accumulate large tool outputs (e.g. a full KB document) that
bloat the context window. Rather than dropping messages — which would break the
assistant ``tool_calls`` ↔ ``tool`` result pairing that both OpenAI and
Anthropic require — we **compact older, oversized message contents in place**,
preserving structure while reclaiming budget. Recent turns are kept verbatim.

This is deterministic and needs no LLM. A token is approximated as ~1 char here
(conservative for CJK); tune ``char_budget`` via config.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..gateway.base import Message

_TRUNCATION_MARK = "…[上下文已压缩]"


@dataclass
class ContextManager:
    char_budget: int = 12000
    keep_recent: int = 6
    min_cap: int = 160

    def size(self, messages: list[Message]) -> int:
        return sum(len(m.content or "") for m in messages)

    def fit(self, messages: list[Message]) -> tuple[list[Message], bool]:
        """Return (messages, compacted). Compacts older contents if over budget."""

        if self.size(messages) <= self.char_budget or len(messages) <= self.keep_recent:
            return messages, False

        cutoff = len(messages) - self.keep_recent
        out: list[Message] = []
        compacted = False
        for i, m in enumerate(messages):
            if i < cutoff and m.content and len(m.content) > self.min_cap:
                out.append(Message(
                    role=m.role,
                    content=m.content[: self.min_cap] + _TRUNCATION_MARK,
                    tool_calls=m.tool_calls,
                    tool_call_id=m.tool_call_id,
                    name=m.name,
                ))
                compacted = True
            else:
                out.append(m)

        # If still over budget, tighten recent tool outputs too (but never the
        # very last message, which is the active turn).
        if self.size(out) > self.char_budget:
            for i in range(len(out) - 1):
                m = out[i]
                if m.role == "tool" and m.content and len(m.content) > self.min_cap:
                    out[i] = Message(role=m.role, content=m.content[: self.min_cap] + _TRUNCATION_MARK,
                                     tool_call_id=m.tool_call_id, name=m.name)
                    compacted = True
        return out, compacted
