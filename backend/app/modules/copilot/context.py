"""Mutable runtime context for a single Copilot turn."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...harness import Tracer
    from ...service import AppServices
    from ..activity_ledger import ActivityLedger


def new_workspace() -> dict[str, Any]:
    return {
        "resume_text": "",
        "job_text": "",
        "company": "",
        "role": "",
        "language": "zh",
        "jobs": [],
        "time_budget": {"weeks": 4, "hours_per_week": 10},
        "learning_progress": {},
        "role_assessments": [],
        "interview_transcript": "",
        "interview_session_id": "",
    }


def new_session(title: str = "新对话") -> dict[str, Any]:
    now = time.time()
    return {
        "id": uuid.uuid4().hex[:12],
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
        "workspace": new_workspace(),
        "artifacts": [],
        "pending_proposal": None,
        "proposal_approved_id": None,
    }


def touch_session_meta(session: dict[str, Any], hint: str = "") -> None:
    """Auto-title session from company or first user text."""
    ws = session.get("workspace") or {}
    title = session.get("title") or "新对话"
    if title != "新对话" and not hint:
        return
    if ws.get("company"):
        session["title"] = str(ws["company"])[:48]
    elif hint:
        session["title"] = hint.strip().replace("\n", " ")[:48]
    session["updated_at"] = time.time()


@dataclass
class CopilotContext:
    session: dict[str, Any]
    services: AppServices
    tracer: Tracer
    ledger: ActivityLedger
    events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def session_id(self) -> str:
        return str(self.session["id"])

    @property
    def workspace(self) -> dict[str, Any]:
        return self.session["workspace"]

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def add_message(self, role: str, content: str) -> None:
        self.session["messages"].append({
            "role": role, "content": content, "ts": time.time(),
        })
        if role == "user":
            touch_session_meta(self.session, content)
        self.session["updated_at"] = time.time()

    def add_artifact(self, kind: str, data: dict[str, Any]) -> str:
        art_id = uuid.uuid4().hex[:10]
        art = {"id": art_id, "kind": kind, "data": data, "created_at": time.time()}
        self.session["artifacts"].append(art)
        self.emit({"type": "artifact", "artifact": art})
        return art_id

    def log_activity(self, kind: str, summary: str, **meta: Any) -> None:
        self.ledger.record(
            kind, summary, session_id=self.session_id, module="copilot", meta=meta or None,
        )

    def set_proposal(self, kind: str, preview: str, inputs: dict[str, Any]) -> str:
        prop_id = uuid.uuid4().hex[:10]
        prop = {"id": prop_id, "kind": kind, "preview": preview, "inputs": inputs}
        self.session["pending_proposal"] = prop
        self.emit({"type": "proposal", "proposal": prop})
        return prop_id

    def consume_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        prop = self.session.get("pending_proposal")
        if not prop or prop.get("id") != proposal_id:
            return None
        self.session["pending_proposal"] = None
        self.session["proposal_approved_id"] = proposal_id
        return prop
