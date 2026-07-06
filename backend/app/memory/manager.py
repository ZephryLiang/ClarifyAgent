"""Memory manager: store, dedupe/reinforce, and search long-term memories.

Consistent with the project's "agentic search over a bounded corpus" stance, we
do **not** use embeddings. Deduplication and retrieval use normalized token
overlap (Jaccard), which is robust for the short, factual strings memories tend
to be. Recurring items are merged and their ``salience`` incremented, so
frequently-seen insights naturally rise to the top.
"""

from __future__ import annotations

import builtins
import json
import re
import time
import uuid

from ..storage import Store
from .models import MEMORY_KINDS, MemoryItem

_TOKEN_RE = re.compile(r"[0-9a-zA-Z\u4e00-\u9fff]+")
_DEDUP_THRESHOLD = 0.82


def _normalize(text: str) -> str:
    return " ".join(_TOKEN_RE.findall(text.lower()))


def _tokens(norm: str) -> set:
    if not norm:
        return set()
    toks = set(norm.split())
    # For CJK-heavy text also include char bigrams for better overlap.
    compact = norm.replace(" ", "")
    toks |= {compact[i:i + 2] for i in range(len(compact) - 1)}
    return toks


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class MemoryManager:
    def __init__(self, store: Store) -> None:
        self.store = store

    def _row_to_item(self, row: dict) -> MemoryItem:
        return MemoryItem(
            id=row["id"], kind=row["kind"], content=row["content"],
            tags=[t for t in (row.get("tags") or "").split(",") if t],
            source=row.get("source") or "", salience=row.get("salience", 1),
            created_at=row.get("created_at", 0.0), updated_at=row.get("updated_at", 0.0),
            meta=json.loads(row["meta_json"]) if row.get("meta_json") else {},
        )

    def add(self, content: str, kind: str = "insight", tags: builtins.list[str] | None = None,
            source: str = "") -> MemoryItem:
        """Add a memory, reinforcing an existing near-duplicate if found."""

        content = content.strip()
        kind = kind if kind in MEMORY_KINDS else "insight"
        tags = tags or []
        norm = _normalize(content)
        now = time.time()

        existing = self.store.mem_all(kind)
        my_tokens = _tokens(norm)
        for row in existing:
            if _jaccard(my_tokens, _tokens(row.get("norm") or _normalize(row["content"]))) >= _DEDUP_THRESHOLD:
                merged_tags = sorted(set(tags) | {t for t in (row.get("tags") or "").split(",") if t})
                self.store.mem_reinforce(row["id"], ",".join(merged_tags), now)
                updated = self._row_to_item(row)
                updated.salience += 1
                updated.tags = merged_tags
                updated.updated_at = now
                return updated

        item = MemoryItem(id=uuid.uuid4().hex[:12], kind=kind, content=content, tags=tags,
                          source=source, salience=1, created_at=now, updated_at=now)
        self.store.mem_insert({
            "id": item.id, "kind": item.kind, "content": item.content, "norm": norm,
            "tags": ",".join(tags), "source": source, "salience": 1,
            "created_at": now, "updated_at": now, "meta_json": None,
        })
        return item

    def search(self, query: str, kind: str | None = None, limit: int = 8) -> builtins.list[MemoryItem]:
        q_tokens = _tokens(_normalize(query))
        scored: list[tuple] = []
        for row in self.store.mem_all(kind):
            norm = row.get("norm") or _normalize(row["content"])
            score = _jaccard(q_tokens, _tokens(norm))
            # small salience boost so reinforced memories rank higher on ties
            score += min(row.get("salience", 1), 10) * 0.01
            if score > 0:
                scored.append((score, row))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [self._row_to_item(r) for _, r in scored[:limit]]

    def list(self, kind: str | None = None) -> builtins.list[MemoryItem]:
        return [self._row_to_item(r) for r in self.store.mem_all(kind)]

    def top(self, limit: int = 10) -> builtins.list[MemoryItem]:
        return self.list()[:limit]

    def update(self, mem_id: str, content: str, tags: builtins.list[str] | None = None) -> bool:
        tags = tags or []
        return self.store.mem_update(mem_id, content.strip(), _normalize(content),
                                     ",".join(tags), time.time())

    def delete(self, mem_id: str) -> bool:
        return self.store.mem_delete(mem_id)
