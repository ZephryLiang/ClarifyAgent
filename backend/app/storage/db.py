"""Lightweight SQLite persistence for runs, traces, and interview sessions.

Uses the standard-library ``sqlite3`` (no extra dependency). Writes are cheap
and infrequent, so a single shared connection guarded by a lock is sufficient.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ..config import DB_PATH


class Store:
    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = str(path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    trace_id TEXT,
                    module TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    input_json TEXT,
                    result_json TEXT,
                    trace_json TEXT
                );
                CREATE TABLE IF NOT EXISTS interview_sessions (
                    id TEXT PRIMARY KEY,
                    updated_at REAL NOT NULL,
                    data_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    norm TEXT NOT NULL,
                    tags TEXT,
                    source TEXT,
                    salience INTEGER NOT NULL DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    meta_json TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_runs_module ON runs(module, created_at);
                CREATE INDEX IF NOT EXISTS idx_mem_kind ON memories(kind, salience);
                """
            )
            self._conn.commit()

    # -- runs --------------------------------------------------------------- #

    def save_run(self, module: str, input_data: dict[str, Any], result: dict[str, Any],
                 trace: dict[str, Any] | None = None) -> str:
        run_id = uuid.uuid4().hex[:12]
        trace_id = (trace or {}).get("trace_id")
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs (id, trace_id, module, created_at, input_json, result_json, trace_json)"
                " VALUES (?,?,?,?,?,?,?)",
                (run_id, trace_id, module, time.time(),
                 json.dumps(input_data, ensure_ascii=False),
                 json.dumps(result, ensure_ascii=False),
                 json.dumps(trace, ensure_ascii=False) if trace else None),
            )
            self._conn.commit()
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return self._row_to_run(row) if row else None

    def list_runs(self, module: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            if module:
                rows = self._conn.execute(
                    "SELECT id, trace_id, module, created_at FROM runs WHERE module=?"
                    " ORDER BY created_at DESC LIMIT ?", (module, limit)).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT id, trace_id, module, created_at FROM runs"
                    " ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "trace_id": row["trace_id"],
            "module": row["module"],
            "created_at": row["created_at"],
            "input": json.loads(row["input_json"]) if row["input_json"] else None,
            "result": json.loads(row["result_json"]) if row["result_json"] else None,
            "trace": json.loads(row["trace_json"]) if row["trace_json"] else None,
        }

    # -- interview sessions ------------------------------------------------- #

    def save_session(self, session_id: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO interview_sessions (id, updated_at, data_json) VALUES (?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, data_json=excluded.data_json",
                (session_id, time.time(), json.dumps(data, ensure_ascii=False)),
            )
            self._conn.commit()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT data_json FROM interview_sessions WHERE id=?", (session_id,)).fetchone()
        return json.loads(row["data_json"]) if row else None

    # -- memories ----------------------------------------------------------- #

    def mem_insert(self, row: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO memories (id, kind, content, norm, tags, source, salience,"
                " created_at, updated_at, meta_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (row["id"], row["kind"], row["content"], row["norm"], row.get("tags"),
                 row.get("source"), row.get("salience", 1), row["created_at"],
                 row["updated_at"], row.get("meta_json")),
            )
            self._conn.commit()

    def mem_reinforce(self, mem_id: str, tags: str, updated_at: float) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE memories SET salience = salience + 1, tags=?, updated_at=? WHERE id=?",
                (tags, updated_at, mem_id),
            )
            self._conn.commit()

    def mem_update(self, mem_id: str, content: str, norm: str, tags: str, updated_at: float) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE memories SET content=?, norm=?, tags=?, updated_at=? WHERE id=?",
                (content, norm, tags, updated_at, mem_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def mem_delete(self, mem_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM memories WHERE id=?", (mem_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def mem_all(self, kind: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if kind:
                rows = self._conn.execute(
                    "SELECT * FROM memories WHERE kind=? ORDER BY salience DESC, updated_at DESC",
                    (kind,)).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM memories ORDER BY salience DESC, updated_at DESC").fetchall()
        return [dict(r) for r in rows]

    def runs_since(self, since_ts: float) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, trace_id, module, created_at, input_json, result_json FROM runs"
                " WHERE created_at >= ? ORDER BY created_at ASC", (since_ts,)).fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"], "module": r["module"], "created_at": r["created_at"],
                "input": json.loads(r["input_json"]) if r["input_json"] else None,
                "result": json.loads(r["result_json"]) if r["result_json"] else None,
            })
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()
