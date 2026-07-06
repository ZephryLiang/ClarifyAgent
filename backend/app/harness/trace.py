"""Observability primitives: spans, traces, and a streaming event bus.

Every meaningful step in the agent — an LLM call, a tool invocation, a spawned
subagent — is recorded as a :class:`Span`. Spans form a tree via ``parent_id``
and belong to a :class:`Trace`. A :class:`Tracer` also exposes an async event
stream so the API layer can forward live updates to the frontend over SSE.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SpanKind(str, Enum):
    AGENT = "agent"
    SUBAGENT = "subagent"
    LLM = "llm"
    TOOL = "tool"
    MCP = "mcp"
    RETRIEVAL = "retrieval"


class SpanStatus(str, Enum):
    RUNNING = "running"
    OK = "ok"
    ERROR = "error"


def _now_ms() -> float:
    return time.time() * 1000.0


@dataclass
class Span:
    name: str
    kind: SpanKind
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    parent_id: Optional[str] = None
    status: SpanStatus = SpanStatus.RUNNING
    start_ms: float = field(default_factory=_now_ms)
    end_ms: Optional[float] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    tokens: int = 0
    error: Optional[str] = None

    @property
    def duration_ms(self) -> Optional[float]:
        if self.end_ms is None:
            return None
        return round(self.end_ms - self.start_ms, 1)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["status"] = self.status.value
        d["duration_ms"] = self.duration_ms
        return d


class Tracer:
    """Collects spans for a single agent run and streams events.

    The tracer is safe to use from async code. Events are pushed onto an
    ``asyncio.Queue`` that the SSE endpoint drains. When no event loop / consumer
    is present (e.g. in unit tests) events are simply buffered in ``spans``.
    """

    def __init__(self, trace_id: Optional[str] = None) -> None:
        self.trace_id = trace_id or uuid.uuid4().hex[:12]
        self.spans: List[Span] = []
        self._queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()
        self._start = _now_ms()

    # -- span lifecycle ----------------------------------------------------- #

    def start_span(self, name: str, kind: SpanKind, parent_id: Optional[str] = None,
                   **attributes: Any) -> Span:
        span = Span(name=name, kind=kind, parent_id=parent_id, attributes=dict(attributes))
        self.spans.append(span)
        self._emit("span_start", span)
        return span

    def end_span(self, span: Span, status: SpanStatus = SpanStatus.OK,
                 error: Optional[str] = None, tokens: int = 0, **attributes: Any) -> None:
        span.end_ms = _now_ms()
        span.status = status
        span.error = error
        span.tokens += tokens
        span.attributes.update(attributes)
        self._emit("span_end", span)

    # -- events ------------------------------------------------------------- #

    def log(self, message: str, **data: Any) -> None:
        event = {"type": "log", "trace_id": self.trace_id, "message": message,
                 "ts": _now_ms(), **data}
        self._safe_put(event)

    def _emit(self, event_type: str, span: Span) -> None:
        self._safe_put({"type": event_type, "trace_id": self.trace_id, "span": span.to_dict()})

    def _safe_put(self, event: Dict[str, Any]) -> None:
        try:
            self._queue.put_nowait(event)
        except Exception:
            # No consumer / full queue — spans remain available via ``spans``.
            pass

    async def events(self):
        """Async generator yielding events until ``close()`` is called."""

        while True:
            event = await self._queue.get()
            if event.get("type") == "__end__":
                break
            yield event

    def close(self) -> None:
        self._safe_put({"type": "__end__", "trace_id": self.trace_id})

    # -- summary ------------------------------------------------------------ #

    def summary(self) -> Dict[str, Any]:
        total_tokens = sum(s.tokens for s in self.spans)
        return {
            "trace_id": self.trace_id,
            "duration_ms": round(_now_ms() - self._start, 1),
            "span_count": len(self.spans),
            "total_tokens": total_tokens,
            "spans": [s.to_dict() for s in self.spans],
        }
