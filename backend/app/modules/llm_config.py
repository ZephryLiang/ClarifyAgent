"""LLM provider configuration helpers (UI + persisted keys)."""

from __future__ import annotations

import os
import time
from dataclasses import replace
from typing import Any

from ..config import ProviderConfig, Settings, reload_settings
from ..gateway.base import Message, ProviderError
from ..gateway.registry import build_provider


def mask_api_key(key: str | None) -> str | None:
    if not key:
        return None
    key = key.strip()
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}…{key[-4:]}"


def apply_stored_provider_config(settings: Settings, stored_keys: dict[str, Any] | None) -> None:
    stored_keys = stored_keys or {}
    for p in settings.providers:
        entry = stored_keys.get(p.name)
        if not entry:
            continue
        if entry.get("api_key"):
            p.api_key = str(entry["api_key"])
        if entry.get("model"):
            p.model = str(entry["model"])
        if entry.get("base_url"):
            p.base_url = str(entry["base_url"])


def apply_stored_priority(settings: Settings, priority: Any) -> None:
    all_names = [p.name for p in settings.providers]
    if isinstance(priority, list) and priority:
        merged: list[str] = []
        seen: set[str] = set()
        for name in priority:
            n = str(name)
            if n in all_names and n not in seen:
                merged.append(n)
                seen.add(n)
        for n in all_names:
            if n not in seen:
                merged.append(n)
        settings.provider_priority = merged


def provider_catalog(settings: Settings, stored_keys: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    stored_keys = stored_keys or {}
    out: list[dict[str, Any]] = []
    for p in settings.providers:
        ui_key = (stored_keys.get(p.name) or {}).get("api_key")
        env_key = os.getenv(p.api_key_env)
        if ui_key:
            source = "ui"
        elif p.api_key and env_key:
            source = "env"
        elif p.api_key:
            source = "ui"
        else:
            source = "none"
        adapter = build_provider(p, settings.request_timeout)
        out.append({
            "name": p.name,
            "protocol": p.protocol,
            "model": p.model,
            "base_url": p.base_url or "",
            "api_key_env": p.api_key_env,
            "configured": bool(p.api_key),
            "available": adapter.available(),
            "api_key_masked": mask_api_key(p.api_key),
            "source": source,
        })
    return out


def reload_settings_with_store(stored_keys: dict | None, priority: Any) -> Settings:
    settings = reload_settings()
    apply_stored_provider_config(settings, stored_keys)
    apply_stored_priority(settings, priority)
    return settings


def resolve_provider_for_test(
    settings: Settings,
    name: str,
    stored_keys: dict[str, Any] | None,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> ProviderConfig:
    base = settings.get_provider(name)
    if base is None:
        raise ValueError(f"unknown provider: {name}")
    entry = (stored_keys or {}).get(name) or {}
    key = (api_key or "").strip() or entry.get("api_key") or base.api_key or os.getenv(base.api_key_env)
    mdl = (model or "").strip() or entry.get("model") or base.model
    url = base_url if base_url is not None else entry.get("base_url") or base.base_url
    if url == "":
        url = base.base_url
    return replace(base, api_key=key, model=mdl, base_url=url or None)


def test_provider_connection(
    settings: Settings,
    name: str,
    stored_keys: dict[str, Any] | None,
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Send a minimal chat to verify credentials (does not persist config)."""
    cfg = resolve_provider_for_test(
        settings, name, stored_keys, api_key=api_key, model=model, base_url=base_url,
    )
    if not cfg.api_key:
        return {"ok": False, "provider": name, "error": "未配置 API Key"}
    adapter = build_provider(cfg, timeout)
    if not adapter.available():
        return {
            "ok": False,
            "provider": name,
            "error": "Provider 不可用（请检查 API Key 或是否已安装 openai/anthropic SDK）",
        }
    t0 = time.perf_counter()
    try:
        resp = adapter.chat(
            [Message(role="user", content="Reply with exactly: ok")],
            temperature=0,
            max_tokens=16,
        )
        ms = int((time.perf_counter() - t0) * 1000)
        preview = (resp.content or "").strip()[:160]
        return {
            "ok": True,
            "provider": name,
            "model": resp.model or cfg.model,
            "protocol": cfg.protocol,
            "latency_ms": ms,
            "reply_preview": preview,
        }
    except ProviderError as exc:
        ms = int((time.perf_counter() - t0) * 1000)
        return {"ok": False, "provider": name, "latency_ms": ms, "error": str(exc)[:500]}
    except Exception as exc:  # noqa: BLE001
        ms = int((time.perf_counter() - t0) * 1000)
        return {
            "ok": False,
            "provider": name,
            "latency_ms": ms,
            "error": f"{type(exc).__name__}: {exc}"[:500],
        }


def list_provider_models(
    settings: Settings,
    name: str,
    stored_keys: dict[str, Any] | None,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """List models via OpenAI-compatible GET /models (Volcengine Ark, DeepSeek, etc.)."""
    cfg = resolve_provider_for_test(
        settings, name, stored_keys, api_key=api_key, base_url=base_url,
    )
    if not cfg.api_key:
        return {"ok": False, "provider": name, "models": [], "error": "未配置 API Key"}
    if cfg.protocol != "openai":
        return {
            "ok": False,
            "provider": name,
            "models": [],
            "error": "该 Provider 暂不支持自动拉取模型列表",
        }
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        return {
            "ok": False,
            "provider": name,
            "models": [],
            "error": "请安装 openai SDK（pip install openai）",
        }
    kwargs: dict[str, Any] = {"api_key": cfg.api_key, "timeout": timeout}
    if cfg.base_url:
        kwargs["base_url"] = cfg.base_url
    client = OpenAI(**kwargs)
    try:
        page = client.models.list()
        models: list[str] = []
        for item in page:
            mid = getattr(item, "id", None)
            if mid:
                models.append(str(mid))
        models.sort(key=lambda m: (0 if m.startswith("ep-") else 1, m))
        return {"ok": True, "provider": name, "models": models}
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "provider": name,
            "models": [],
            "error": str(exc)[:500],
        }
