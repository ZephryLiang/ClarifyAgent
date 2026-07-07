"""Shared helpers for feature modules."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..gateway.registry import Gateway

_KB_ROOT = Path(__file__).resolve().parents[2] / "knowledge_base"


def load_kb_relative(*parts: str) -> str:
    """Load a knowledge-base markdown file; return empty string if missing."""
    try:
        return _KB_ROOT.joinpath(*parts).read_text(encoding="utf-8")
    except OSError:
        return ""


def llm_available(gateway: Gateway | None) -> bool:
    return gateway is not None and gateway.available()


_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def extract_json(text: str) -> Any | None:
    """Best-effort extraction of a JSON object/array from an LLM response.

    Handles fenced code blocks and leading/trailing prose. Returns ``None`` if
    nothing parseable is found.
    """

    if not text:
        return None
    # 1) fenced block
    m = _JSON_FENCE.search(text)
    candidates = []
    if m:
        candidates.append(m.group(1))
    # 2) first {...} or [...] span
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if 0 <= start < end:
            candidates.append(text[start:end + 1])
    # 3) whole string
    candidates.append(text.strip())

    for c in candidates:
        try:
            return json.loads(c)
        except (json.JSONDecodeError, TypeError):
            continue
    return None
