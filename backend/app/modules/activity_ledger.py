"""User activity event ledger (H1 track in flow H)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..storage import Store


class ActivityLedger:
    def __init__(self, store: Store) -> None:
        self.store = store

    def record(
        self,
        kind: str,
        summary: str,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        module: str = "copilot",
        input_ref: str = "",
        artifact_ids: list[str] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str:
        event_id = uuid.uuid4().hex[:12]
        self.store.activity_insert({
            "id": event_id,
            "ts": time.time(),
            "session_id": session_id or "",
            "run_id": run_id or "",
            "kind": kind,
            "module": module,
            "summary": summary[:500],
            "input_ref": input_ref,
            "artifact_ids": artifact_ids or [],
            "meta": meta or {},
        })
        return event_id

    def list_since(
        self, since_ts: float = 0.0, kind: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        return self.store.activity_list(since_ts=since_ts, kind=kind, limit=limit)
