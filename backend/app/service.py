"""Application service layer.

Wires together the gateway, tool registry (built-ins + MCP), storage, and the
feature modules into a single facade the API routes call. Construction is cheap
and dependency-injected so tests can build a service with fakes.
"""

from __future__ import annotations

from typing import Any

from .config import Settings
from .config import settings as default_settings
from .export import ObsidianExporter
from .gateway.registry import Gateway
from .governance import ApprovalManager
from .harness import StoreCheckpointer, ToolRegistry, Tracer
from .mcp import MCPManager
from .memory import MemoryManager
from .modules import (
    Matcher,
    MockInterviewer,
    OutreachWriter,
    ResumeRewriter,
    Retrospective,
)
from .modules.curator import MemoryCurator
from .modules.journal import JournalWriter
from .modules.verify import Judge
from .storage import Store
from .tools import build_registry
from .tools.memory import build_memory_tools


class AppServices:
    def __init__(self, settings: Settings | None = None,
                 gateway: Gateway | None = None,
                 store: Store | None = None) -> None:
        self.settings = settings or default_settings
        self.gateway = gateway or Gateway(self.settings)
        self.tools: ToolRegistry = build_registry()
        self.mcp = MCPManager.from_path(self.settings.mcp_config_path)
        self.store = store or Store()

        # Long-term memory + agentic memory tools.
        self.memory = MemoryManager(self.store)
        for tool in build_memory_tools(self.memory):
            self.tools.register(tool)

        # Governance: HITL approval + audit for side-effecting tools.
        self.approver = ApprovalManager(self.store, self.settings.hitl_policy)
        # Durable execution: checkpointer for resumable agent runs.
        self.checkpointer = StoreCheckpointer(self.store)

        self.rewriter = ResumeRewriter(self.gateway, self.tools, approver=self.approver)
        self.matcher = Matcher(self.gateway, self.tools, approver=self.approver)
        self.outreach = OutreachWriter(self.gateway)
        self.interviewer = MockInterviewer(self.gateway)
        self.retrospective = Retrospective(self.gateway, self.tools, approver=self.approver)
        self.curator = MemoryCurator(self.memory, self.gateway)
        self.journal = JournalWriter(self.store, self.memory, self.gateway)
        self.judge = Judge(self.gateway)
        self.obsidian = ObsidianExporter()
        self._mcp_notes: list[str] = []

    async def reflect_after(self, module: str, input_data: dict[str, Any],
                            result: dict[str, Any], tracer: Tracer) -> None:
        """Best-effort post-run reflection to capture durable memories."""

        if module == "journal":
            return
        await self.curator.reflect(module, input_data, result, tracer)

    async def connect_mcp(self) -> list[str]:
        """Connect configured MCP servers and merge their tools into the registry."""

        self._mcp_notes = await self.mcp.connect()
        for tool in self.mcp.tools():
            self.tools.register(tool)
        return self._mcp_notes

    async def shutdown(self) -> None:
        await self.mcp.aclose()
        self.store.close()

    def status(self) -> dict:
        return {
            "llm_enabled": self.gateway.available(),
            "providers": self.gateway.describe(),
            "tools": self.tools.names(),
            "mcp_notes": self._mcp_notes,
            "default_priority": [p.name for p in self.settings.resolved_priority()],
            "memory_count": len(self.memory.list()),
            "hitl_policy": self.approver.policy,
            "approved_tools": self.approver.approved_tools(),
        }

    def new_tracer(self) -> Tracer:
        return Tracer()
