"""Runtime mode and chat session management tests."""

from __future__ import annotations

import pytest

from app.service import AppServices


@pytest.mark.asyncio
async def test_llm_mode_offline_forces_no_llm():
    svc = AppServices()
    svc.set_llm_mode("offline")
    assert svc.gateway.available() is False
    assert svc.runtime_settings()["llm_mode"] == "offline"


def test_test_provider_no_key():
    from app.config import load_settings
    from app.modules.llm_config import test_provider_connection

    r = test_provider_connection(load_settings(), "deepseek", {})
    assert r["ok"] is False
    assert "Key" in r["error"]


def test_test_provider_success_with_mock():
    from unittest.mock import patch

    from app.config import load_settings
    from app.gateway.base import ChatResponse
    from app.modules.llm_config import test_provider_connection
    from tests.fakes import FakeProvider

    fake = FakeProvider("deepseek", [ChatResponse(content="ok", model="deepseek-chat")])
    with patch("app.modules.llm_config.build_provider", return_value=fake):
        r = test_provider_connection(
            load_settings(), "deepseek", {"deepseek": {"api_key": "sk-test"}},
            api_key="sk-test",
        )
    assert r["ok"] is True
    assert r["latency_ms"] >= 0
    assert fake.calls


def test_list_provider_models_no_key():
    from app.config import load_settings
    from app.modules.llm_config import list_provider_models

    r = list_provider_models(load_settings(), "volcengine", {})
    assert r["ok"] is False
    assert "Key" in r["error"]


def test_list_provider_models_with_mock():
    from unittest.mock import MagicMock, patch

    from app.config import load_settings
    from app.modules.llm_config import list_provider_models

    fake_page = [
        MagicMock(id="ep-20240612090709-hzjz5"),
        MagicMock(id="doubao-1-5-pro-32k-250115"),
    ]
    fake_client = MagicMock()
    fake_client.models.list.return_value = fake_page
    with patch("openai.OpenAI", return_value=fake_client):
        r = list_provider_models(
            load_settings(), "volcengine", {"volcengine": {"api_key": "sk-test"}},
            api_key="sk-test",
        )
    assert r["ok"] is True
    assert r["models"][0].startswith("ep-")


def test_provider_entry_register_and_switch():
    from unittest.mock import patch

    from app.gateway.base import ChatResponse
    from tests.fakes import FakeProvider

    svc = AppServices()
    fake = FakeProvider("deepseek", [ChatResponse(content="ok", model="deepseek-chat")])
    with patch("app.modules.llm_config.build_provider", return_value=fake):
        result = svc.test_provider(
            "deepseek",
            api_key="sk-test-key-12345678",
            model="deepseek-chat",
            register=True,
        )
    assert result["ok"] is True
    assert result.get("registered") is True
    entry_id = result["entry_id"]
    svc.set_active_provider_entry("deepseek", entry_id)
    settings = svc.provider_settings()
    assert settings["active_provider_entry"]["entry_id"] == entry_id
    deepseek = next(p for p in settings["providers"] if p["name"] == "deepseek")
    assert any(e["id"] == entry_id for e in deepseek.get("entries", []))


def test_provider_key_persist_and_reload():
    svc = AppServices()
    result = svc.set_provider_config("deepseek", api_key="sk-test-key-12345678", model="deepseek-chat")
    deepseek = next(p for p in result["providers"] if p["name"] == "deepseek")
    assert deepseek["configured"] is True
    assert deepseek["api_key_masked"] == "sk-t…5678"

    svc2 = AppServices(store=svc.store)
    cat = next(p for p in svc2.provider_settings()["providers"] if p["name"] == "deepseek")
    assert cat["configured"] is True


def test_llm_mode_persists():
    svc = AppServices()
    svc.set_llm_mode("online")
    svc2 = AppServices(store=svc.store)
    assert svc2.gateway.llm_mode == "online"


def test_chat_session_list_and_delete():
    from app.modules.copilot import create_session

    svc = AppServices()
    s1 = create_session("测试对话 A")
    s2 = create_session("测试对话 B")
    svc.store.chat_save(s1["id"], s1)
    svc.store.chat_save(s2["id"], s2)

    listed = svc.store.chat_list(limit=10)
    ids = {x["id"] for x in listed}
    assert s1["id"] in ids
    assert s2["id"] in ids
    assert any(x["title"] == "测试对话 A" for x in listed)

    assert svc.store.chat_delete(s1["id"])
    listed2 = svc.store.chat_list(limit=10)
    assert s1["id"] not in {x["id"] for x in listed2}
