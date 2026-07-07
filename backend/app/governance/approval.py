"""Human-in-the-loop approval policy + audit trail for side-effecting tools.

Side-effecting tools (e.g. MCP actions that message a recruiter or submit an
application) are gated by a policy:

* ``auto``    — allow, but record every action in the audit log.
* ``confirm`` — block by default; a human must pre-approve the tool via the API,
  after which subsequent calls are allowed. (default)
* ``deny``    — never allow side effects.

Read-only tools are always allowed and not audited (keeps the trail signal-rich).
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from ..storage import Store


@dataclass
class ApprovalDecision:
    allowed: bool
    decision: str  # auto_approved | human_approved | blocked_pending_approval | denied
    reason: str = ""


class ApprovalManager:
    def __init__(self, store: Store, policy: str = "confirm") -> None:
        self.store = store
        self.policy = policy if policy in ("auto", "confirm", "deny") else "confirm"
        # Tools a human has explicitly approved for this process lifetime.
        self._approved: set[str] = set()

    def approve_tool(self, tool_name: str) -> None:
        self._approved.add(tool_name)

    def revoke_tool(self, tool_name: str) -> None:
        self._approved.discard(tool_name)

    def approved_tools(self) -> list[str]:
        return sorted(self._approved)

    def check(self, tool_name: str, arguments: dict[str, Any], *,
              actor: str = "agent", trace_id: str | None = None) -> ApprovalDecision:
        """Decide whether a side-effecting tool call may proceed, and audit it."""

        if self.policy == "auto":
            decision = ApprovalDecision(True, "auto_approved")
        elif tool_name in self._approved:
            decision = ApprovalDecision(True, "human_approved")
        elif self.policy == "deny":
            decision = ApprovalDecision(False, "denied",
                                        "治理策略为 deny：禁止副作用操作。")
        else:  # confirm
            decision = ApprovalDecision(
                False, "blocked_pending_approval",
                f"该操作有副作用，需人工确认。请先批准工具 '{tool_name}' 后重试。")

        self._audit(tool_name, arguments, decision, actor, trace_id)
        return decision

    def _audit(self, tool_name: str, arguments: dict[str, Any],
               decision: ApprovalDecision, actor: str, trace_id: str | None) -> None:
        try:
            summary = json.dumps(arguments, ensure_ascii=False)[:400]
        except (TypeError, ValueError):
            summary = str(arguments)[:400]
        self.store.audit_insert({
            "id": uuid.uuid4().hex[:12], "ts": time.time(), "actor": actor,
            "tool": tool_name, "action": "tool_call", "decision": decision.decision,
            "args_summary": summary, "trace_id": trace_id,
        })

    def record(self, action: str, decision: str, *, actor: str = "user",
               tool: str = "", trace_id: str | None = None) -> None:
        """Record an arbitrary governance event (e.g. a human approval)."""

        self.store.audit_insert({
            "id": uuid.uuid4().hex[:12], "ts": time.time(), "actor": actor,
            "tool": tool, "action": action, "decision": decision,
            "args_summary": "", "trace_id": trace_id,
        })
