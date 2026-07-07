"""Tests for the governance layer: HITL approval gate + audit trail."""

import tempfile

import pytest

from app.gateway.registry import Gateway
from app.governance import ApprovalManager
from app.harness import Agent, ToolRegistry, Tracer
from app.storage import Store

from .fakes import FakeProvider, SideEffectTool, text_response, tool_response


def _store() -> Store:
    return Store(tempfile.mktemp(suffix=".db"))


def test_confirm_policy_blocks_side_effect_and_audits():
    store = _store()
    approver = ApprovalManager(store, policy="confirm")
    d = approver.check("send_message", {"to": "hr"}, actor="agent", trace_id="t1")
    assert not d.allowed
    assert d.decision == "blocked_pending_approval"
    entries = store.audit_list()
    assert entries and entries[0]["tool"] == "send_message"


def test_auto_policy_allows_and_audits():
    store = _store()
    approver = ApprovalManager(store, policy="auto")
    d = approver.check("send_message", {}, actor="agent")
    assert d.allowed and d.decision == "auto_approved"
    assert store.audit_list()


def test_human_approval_unblocks():
    store = _store()
    approver = ApprovalManager(store, policy="confirm")
    assert not approver.check("send_message", {}).allowed
    approver.approve_tool("send_message")
    assert approver.check("send_message", {}).allowed


@pytest.mark.asyncio
async def test_agent_gate_blocks_unapproved_side_effect_tool():
    store = _store()
    approver = ApprovalManager(store, policy="confirm")
    tool = SideEffectTool()
    provider = FakeProvider("fake", [
        tool_response("send_message", {"to": "hr"}),
        text_response("done"),
    ])
    agent = Agent(Gateway(providers=[provider]), ToolRegistry([tool]), Tracer(),
                  approver=approver)
    result = await agent.run("greet the recruiter")
    assert result.output == "done"
    assert tool.executed == 0  # blocked, never ran


@pytest.mark.asyncio
async def test_agent_gate_runs_after_approval():
    store = _store()
    approver = ApprovalManager(store, policy="confirm")
    approver.approve_tool("send_message")
    tool = SideEffectTool()
    provider = FakeProvider("fake", [
        tool_response("send_message", {"to": "hr"}),
        text_response("done"),
    ])
    agent = Agent(Gateway(providers=[provider]), ToolRegistry([tool]), Tracer(),
                  approver=approver)
    await agent.run("greet")
    assert tool.executed == 1
