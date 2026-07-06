"""Application service layer.

Wires together the gateway, tool registry (built-ins + MCP), storage, and the
feature modules into a single facade the API routes call. Construction is cheap
and dependency-injected so tests can build a service with fakes.
"""

from __future__ import annotations

from .config import Settings
from .config import settings as default_settings
from .gateway.registry import Gateway
from .harness import ToolRegistry, Tracer
from .mcp import MCPManager
from .modules import (
    Matcher,
    MockInterviewer,
    OutreachWriter,
    ResumeRewriter,
    Retrospective,
)
from .storage import Store
from .tools import build_registry


class AppServices:
    def __init__(self, settings: Settings | None = None,
                 gateway: Gateway | None = None,
                 store: Store | None = None) -> None:
        self.settings = settings or default_settings
        self.gateway = gateway or Gateway(self.settings)
        self.tools: ToolRegistry = build_registry()
        self.mcp = MCPManager.from_path(self.settings.mcp_config_path)
        self.store = store or Store()

        self.rewriter = ResumeRewriter(self.gateway, self.tools)
        self.matcher = Matcher(self.gateway, self.tools)
        self.outreach = OutreachWriter(self.gateway)
        self.interviewer = MockInterviewer(self.gateway)
        self.retrospective = Retrospective(self.gateway, self.tools)
        self._mcp_notes: list[str] = []

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
        }

    def new_tracer(self) -> Tracer:
        return Tracer()
