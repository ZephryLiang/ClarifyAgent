"""Tests for the memory subsystem, curator, and journal."""

import tempfile

import pytest

from app.memory import MemoryManager
from app.modules.curator import MemoryCurator
from app.modules.journal import JournalWriter
from app.storage import Store


def _store() -> Store:
    return Store(tempfile.mktemp(suffix=".db"))


def test_add_dedupes_and_reinforces():
    mm = MemoryManager(_store())
    mm.add("目标岗位常要求但简历尚缺: Kafka", kind="recurring", tags=["Kafka"])
    again = mm.add("目标岗位常要求但简历尚缺: Kafka", kind="recurring", tags=["mq"])
    assert again.salience == 2
    assert "Kafka" in again.tags and "mq" in again.tags
    # only one row persisted
    assert len(mm.list("recurring")) == 1


def test_search_ranks_relevant_first():
    mm = MemoryManager(_store())
    mm.add("用 STAR 法则描述项目", kind="principle")
    mm.add("补齐 Kubernetes 技能", kind="recurring", tags=["k8s"])
    results = mm.search("Kubernetes")
    assert results
    assert "Kubernetes" in results[0].content


def test_update_and_delete():
    mm = MemoryManager(_store())
    item = mm.add("原始内容", kind="insight")
    assert mm.update(item.id, "更新后的内容", ["t"])
    assert mm.list()[0].content == "更新后的内容"
    assert mm.delete(item.id)
    assert mm.list() == []


@pytest.mark.asyncio
async def test_curator_offline_extracts_skill_gaps():
    mm = MemoryManager(_store())
    curator = MemoryCurator(mm, gateway=None)
    items = await curator.reflect(
        "matching", {"job_text": "x"},
        {"match": {"missing_required": ["Kafka", "Spark"]}},
    )
    assert {i.content for i in items}
    assert any("Kafka" in i.content for i in items)


@pytest.mark.asyncio
async def test_journal_offline_reports_recurring():
    store = _store()
    mm = MemoryManager(store)
    mm.add("补齐 Kafka", kind="recurring", tags=["Kafka", "skill-gap"])
    mm.add("补齐 Kafka", kind="recurring", tags=["Kafka", "skill-gap"])  # reinforce
    journal = JournalWriter(store, mm, gateway=None)
    result = await journal.run()
    assert result.date
    assert "今日求职日报" in result.markdown
    assert "Kafka" in result.markdown
