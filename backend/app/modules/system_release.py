"""System release / change log (H2 track in flow H)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from ..config import APP_VERSION
from ..storage import Store


class SystemReleaseLog:
    def __init__(self, store: Store) -> None:
        self.store = store

    def ensure_seeded(self) -> None:
        if self.store.system_release_list(limit=1):
            return
        self.store.system_release_insert({
            "id": uuid.uuid4().hex[:12],
            "version": "0.1.0",
            "released_at": time.time() - 86400 * 30,
            "title": "Tab 模块 + Agent Harness 基线",
            "summary": "简历改写、匹配、打招呼、模拟面试、复盘、记忆日报",
            "details_path": "docs/releases/v0.1.0-baseline.md",
            "features": ["resume_rewrite", "matching", "outreach", "interview", "memory"],
            "breaking": [],
        })
        self.store.system_release_insert({
            "id": uuid.uuid4().hex[:12],
            "version": APP_VERSION,
            "released_at": time.time(),
            "title": "Copilot 对话入口 + 多 JD 学习计划",
            "summary": "Chat-first Copilot、Gap 桥接、技术调研、学习计划、双轨记录",
            "details_path": "docs/releases/v0.2.0-copilot.md",
            "features": [
                "copilot", "jd_analysis", "gap_bridge", "tech_research",
                "learning_plan", "activity_ledger", "weekly_journal",
            ],
            "breaking": [],
        })

    def record_change(
        self,
        summary: str,
        *,
        category: str = "feature",
        component: str = "copilot",
        version: str | None = None,
    ) -> str:
        cid = uuid.uuid4().hex[:12]
        self.store.system_change_insert({
            "id": cid,
            "ts": time.time(),
            "version": version or APP_VERSION,
            "category": category,
            "component": component,
            "summary": summary[:400],
        })
        return cid

    def list_releases(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.store.system_release_list(limit=limit)

    def list_changes_since(self, since_ts: float, limit: int = 100) -> list[dict[str, Any]]:
        return self.store.system_change_list(since_ts=since_ts, limit=limit)

    def current_version(self) -> dict[str, str]:
        releases = self.store.system_release_list(limit=1)
        if releases:
            r = releases[0]
            return {"version": r["version"], "title": r.get("title", "")}
        return {"version": APP_VERSION, "title": ""}
