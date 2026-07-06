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
from typing import Any, Dict, List, Optional

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
                CREATE INDEX IF NOT EXISTS idx_runs_module ON runs(module, created_at);
                """
            )
            self._conn.commit()

    # -- runs --------------------------------------------------------------- #

    def save_run(self, module: str, input_data: Dict[str, Any], result: Dict[str, Any],
                 trace: Optional[Dict[str, Any]] = None) -> str:
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

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return self._row_to_run(row) if row else None

    def list_runs(self, module: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
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
    def _row_to_run(row: sqlite3.Row) -> Dict[str, Any]:
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

    def save_session(self, session_id: str, data: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO interview_sessions (id, updated_at, data_json) VALUES (?,?,?)"
                " ON CONFLICT(id) DO UPDATE SET updated_at=excluded.updated_at, data_json=excluded.data_json",
                (session_id, time.time(), json.dumps(data, ensure_ascii=False)),
            )
            self._conn.commit()

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT data_json FROM interview_sessions WHERE id=?", (session_id,)).fetchone()
        return json.loads(row["data_json"]) if row else None

    def close(self) -> None:
        with self._lock:
            self._conn.close()
