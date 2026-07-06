"""Memory data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Recognised memory kinds. ``insight``/``principle`` are durable knowledge;
# ``preference`` captures stable user choices; ``fact`` is a concrete detail;
# ``recurring`` is anything reinforced repeatedly.
MEMORY_KINDS = ("insight", "principle", "preference", "fact", "recurring")


@dataclass
class MemoryItem:
    id: str
    kind: str
    content: str
    tags: list[str] = field(default_factory=list)
    source: str = ""
    salience: int = 1
    created_at: float = 0.0
    updated_at: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "content": self.content,
            "tags": self.tags,
            "source": self.source,
            "salience": self.salience,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "meta": self.meta,
        }
