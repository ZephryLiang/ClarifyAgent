"""Persisted LLM provider entries — multiple registered configs per provider."""

from __future__ import annotations

import time
import uuid
from typing import Any

from dataclasses import replace

from ..config import ProviderConfig, Settings
from .llm_config import mask_api_key, build_provider


def empty_registry() -> dict[str, Any]:
    return {"entries": {}, "active": None}


def load_registry(raw: Any, legacy_keys: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(raw, dict) and isinstance(raw.get("entries"), dict) and raw.get("entries"):
        return {"entries": dict(raw["entries"]), "active": raw.get("active")}
    reg = empty_registry()
    if legacy_keys:
        for name, cfg in legacy_keys.items():
            if not isinstance(cfg, dict) or not cfg.get("api_key"):
                continue
            reg["entries"].setdefault(name, []).append(
                _new_entry(
                    api_key=str(cfg["api_key"]),
                    model=str(cfg.get("model") or ""),
                    base_url=str(cfg.get("base_url") or ""),
                    label=str(cfg.get("model") or name),
                )
            )
        if reg["entries"] and not reg["active"]:
            first_name = next(iter(reg["entries"]))
            first_entry = reg["entries"][first_name][0]
            reg["active"] = {"provider": first_name, "entry_id": first_entry["id"]}
    return reg


def _new_entry(
    *,
    api_key: str,
    model: str,
    base_url: str,
    label: str,
    latency_ms: int | None = None,
) -> dict[str, Any]:
    now = time.time()
    return {
        "id": uuid.uuid4().hex[:12],
        "label": label or model or "default",
        "api_key": api_key.strip(),
        "model": model.strip(),
        "base_url": base_url.strip(),
        "created_at": now,
        "tested_at": now,
        "latency_ms": latency_ms,
    }


def find_entry(registry: dict[str, Any], provider: str, entry_id: str) -> dict[str, Any] | None:
    for ent in registry.get("entries", {}).get(provider, []):
        if ent.get("id") == entry_id:
            return ent
    return None


def register_entry(
    registry: dict[str, Any],
    provider: str,
    *,
    api_key: str,
    model: str,
    base_url: str,
    label: str | None = None,
    latency_ms: int | None = None,
    set_active: bool = True,
) -> dict[str, Any]:
    entries = registry.setdefault("entries", {}).setdefault(provider, [])
    label = (label or model or provider).strip()
    for ent in entries:
        if (
            ent.get("api_key") == api_key.strip()
            and ent.get("model", "") == model.strip()
            and ent.get("base_url", "") == base_url.strip()
        ):
            ent["tested_at"] = time.time()
            if latency_ms is not None:
                ent["latency_ms"] = latency_ms
            if set_active:
                registry["active"] = {"provider": provider, "entry_id": ent["id"]}
            return ent
    ent = _new_entry(
        api_key=api_key,
        model=model,
        base_url=base_url,
        label=label,
        latency_ms=latency_ms,
    )
    entries.append(ent)
    if set_active:
        registry["active"] = {"provider": provider, "entry_id": ent["id"]}
    return ent


def delete_entry(registry: dict[str, Any], provider: str, entry_id: str) -> bool:
    entries = registry.get("entries", {}).get(provider, [])
    new_list = [e for e in entries if e.get("id") != entry_id]
    if len(new_list) == len(entries):
        return False
    if new_list:
        registry["entries"][provider] = new_list
    else:
        registry.get("entries", {}).pop(provider, None)
    active = registry.get("active")
    if active and active.get("provider") == provider and active.get("entry_id") == entry_id:
        registry["active"] = _pick_default_active(registry)
    return True


def set_active_entry(registry: dict[str, Any], provider: str, entry_id: str) -> None:
    if find_entry(registry, provider, entry_id) is None:
        raise ValueError(f"entry not found: {provider}/{entry_id}")
    registry["active"] = {"provider": provider, "entry_id": entry_id}


def pick_default_active(registry: dict[str, Any]) -> dict[str, str] | None:
    return _pick_default_active(registry)


def _pick_default_active(registry: dict[str, Any]) -> dict[str, str] | None:
    for provider, entries in registry.get("entries", {}).items():
        if entries:
            return {"provider": provider, "entry_id": entries[0]["id"]}
    return None


def apply_registry_to_settings(settings: Settings, registry: dict[str, Any]) -> str | None:
    """Apply registered entries to provider configs; return active provider name."""
    entries_map: dict[str, list[dict[str, Any]]] = registry.get("entries") or {}
    active = registry.get("active")
    active_provider: str | None = None

    for pname, entries in entries_map.items():
        p = settings.get_provider(pname)
        if p is None or not entries:
            continue
        ent: dict[str, Any] | None = None
        if active and active.get("provider") == pname:
            ent = find_entry(registry, pname, str(active.get("entry_id", "")))
            if ent:
                active_provider = pname
        if ent is None:
            ent = entries[0]
        p.api_key = ent.get("api_key")
        if ent.get("model"):
            p.model = str(ent["model"])
        if ent.get("base_url"):
            p.base_url = str(ent["base_url"]) or None

    if active_provider:
        prio = list(settings.provider_priority)
        prio = [active_provider] + [x for x in prio if x != active_provider]
        settings.provider_priority = prio
    return active_provider


def serialize_entry(ent: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": ent.get("id"),
        "label": ent.get("label"),
        "model": ent.get("model"),
        "base_url": ent.get("base_url") or "",
        "api_key_masked": mask_api_key(ent.get("api_key")),
        "created_at": ent.get("created_at"),
        "tested_at": ent.get("tested_at"),
        "latency_ms": ent.get("latency_ms"),
    }


def catalog_with_entries(
    settings: Settings,
    registry: dict[str, Any],
    *,
    request_timeout: float,
) -> list[dict[str, Any]]:
    from .llm_config import provider_catalog

    legacy = {}
    for pname, entries in (registry.get("entries") or {}).items():
        if entries:
            legacy[pname] = entries[0]
    base = provider_catalog(settings, legacy)
    active = registry.get("active")
    by_name = {p["name"]: p for p in base}
    out: list[dict[str, Any]] = []
    for p in settings.providers:
        item = dict(by_name.get(p.name, {
            "name": p.name,
            "protocol": p.protocol,
            "model": p.model,
            "base_url": p.base_url or "",
            "api_key_env": p.api_key_env,
            "configured": False,
            "available": False,
            "api_key_masked": None,
            "source": "none",
        }))
        entries = registry.get("entries", {}).get(p.name, [])
        item["entries"] = [serialize_entry(e) for e in entries]
        item["entry_count"] = len(entries)
        if active and active.get("provider") == p.name:
            item["active_entry_id"] = active.get("entry_id")
        if entries:
            item["configured"] = True
            item["source"] = "ui"
            ent = find_entry(registry, p.name, str(active.get("entry_id", ""))) if active else entries[0]
            use = ent or entries[0]
            cfg = replace(
                p,
                api_key=use.get("api_key"),
                model=str(use.get("model") or p.model),
                base_url=str(use.get("base_url") or p.base_url or "") or None,
            )
            adapter = build_provider(cfg, request_timeout)
            item["available"] = adapter.available()
            item["api_key_masked"] = mask_api_key(use.get("api_key"))
            item["model"] = cfg.model
        out.append(item)
    return out
