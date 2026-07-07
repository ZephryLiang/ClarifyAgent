"""Persist high-value tech research sources as heuristic memories."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .tech_research import TechResearchDigest

if TYPE_CHECKING:
    from ..memory import MemoryManager

_SCORE_THRESHOLD = 55.0


class ResearchCurator:
    def __init__(self, memory: MemoryManager) -> None:
        self.memory = memory

    def curate(self, digest: TechResearchDigest) -> list[str]:
        """Store top-scored sources as ``heuristic`` memories; return memory ids."""
        ids: list[str] = []
        for src in digest.sources:
            if src.score < _SCORE_THRESHOLD or not src.snippet.strip():
                continue
            content = f"[{digest.theme}] {src.title}: {src.snippet[:240]}"
            tags = ["tech_research", digest.theme.replace(" ", "_")[:32], src.source_type]
            item = self.memory.add(
                content,
                kind="heuristic",
                tags=tags,
                source=src.url or "tech_research",
            )
            ids.append(item.id)
        return ids
