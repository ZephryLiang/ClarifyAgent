"""Export summaries/journals to an Obsidian vault as Markdown.

Obsidian reads plain ``.md`` files from a folder, so the default path just
writes files into the configured vault directory — zero dependencies. If an
Obsidian MCP server is configured, an agent can alternatively call its tools;
that path plugs into the existing MCP client and needs no code here.

Filenames are slugified and confined to the vault directory.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from ..config import OBSIDIAN_VAULT_DIR

_SLUG_RE = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")


def _slug(text: str) -> str:
    s = _SLUG_RE.sub("-", text.strip()).strip("-")
    return s[:80] or "note"


class ObsidianExporter:
    def __init__(self, vault_dir: Path | str = OBSIDIAN_VAULT_DIR) -> None:
        self.vault_dir = Path(vault_dir)

    def write(self, title: str, content: str, subdir: str = "求职Agent",
              tags: list | None = None) -> str:
        """Write a markdown note; returns the absolute file path."""

        folder = (self.vault_dir / subdir).resolve()
        vault_resolved = self.vault_dir.resolve()
        if vault_resolved != folder and vault_resolved not in folder.parents:
            folder = vault_resolved  # never escape the vault
        folder.mkdir(parents=True, exist_ok=True)

        date = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date}-{_slug(title)}.md"
        path = folder / filename

        front_matter = [
            "---",
            f"title: {title}",
            f"date: {date}",
            "tags: [" + ", ".join(tags or ["求职", "jobseeker"]) + "]",
            "---",
            "",
        ]
        path.write_text("\n".join(front_matter) + content + "\n", encoding="utf-8")
        return str(path)
