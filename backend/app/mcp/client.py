"""MCP (Model Context Protocol) client.

Lets the harness consume tools exposed by *external* MCP servers — e.g. the
community job-platform servers ``boss-agent-cli`` (BOSS直聘/智联/51job) or
``linkedin-mcp-server`` (外企) — without us scraping anything ourselves.
Compliance and authentication (the user's own logged-in browser session) stay
with those upstream servers; we only speak MCP to them.

Config format mirrors Claude Desktop / Cursor (``mcpServers``):

    {
      "mcpServers": {
        "boss-agent": {"command": "uvx", "args": ["--from", "boss-agent-cli[mcp]", "boss-mcp"]},
        "linkedin":   {"command": "python", "args": ["/path/to/linkedin_server.py"]}
      }
    }

The client degrades gracefully: if the ``mcp`` SDK is not installed or a server
cannot be reached, it logs and continues with zero MCP tools.
"""

from __future__ import annotations

import json
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from ..harness.tools import Tool, ToolResult


def load_mcp_config(path: str | Path) -> dict[str, dict[str, Any]]:
    """Read an ``mcpServers`` config file and return the server map."""

    p = Path(path)
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("mcpServers", data) or {}


class MCPTool(Tool):
    """Wraps a single remote MCP tool behind our :class:`Tool` interface."""

    def __init__(self, manager: MCPManager, server: str, name: str,
                 description: str, parameters: dict[str, Any]) -> None:
        # Namespace the tool so multiple servers can expose same-named tools.
        self.name = f"{server}__{name}"
        self.remote_name = name
        self.server = server
        self.description = f"[MCP:{server}] {description}"
        self.parameters = parameters or {"type": "object", "properties": {}}
        # Conservatively treat write-like remote tools as side-effecting so the
        # governance layer gates them (e.g. greeting a recruiter, applying).
        lowered = name.lower()
        self.side_effect = any(k in lowered for k in (
            "greet", "send", "apply", "message", "post", "submit",
            "create", "update", "delete", "write", "reply", "invite",
        ))
        self._manager = manager

    async def run(self, **kwargs: Any) -> ToolResult:
        return await self._manager.call_tool(self.server, self.remote_name, kwargs)


class MCPManager:
    """Connects to configured MCP servers and surfaces their tools."""

    def __init__(self, config: dict[str, dict[str, Any]] | None = None) -> None:
        self.config = config or {}
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, Any] = {}
        self._tools: list[MCPTool] = []

    @classmethod
    def from_path(cls, path: str | Path | None) -> MCPManager:
        if not path:
            return cls({})
        return cls(load_mcp_config(path))

    def sdk_available(self) -> bool:
        try:
            import mcp  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False

    async def connect(self) -> list[str]:
        """Connect to all configured servers. Returns notes for observability."""

        notes: list[str] = []
        if not self.config:
            return ["未配置 MCP server"]
        if not self.sdk_available():
            return ["未安装 mcp SDK (pip install mcp)，跳过 MCP 工具"]

        from mcp import ClientSession, StdioServerParameters  # type: ignore
        from mcp.client.stdio import stdio_client  # type: ignore

        self._stack = AsyncExitStack()
        for server, cfg in self.config.items():
            try:
                params = StdioServerParameters(
                    command=cfg["command"],
                    args=cfg.get("args", []),
                    env=cfg.get("env"),
                )
                read, write = await self._stack.enter_async_context(stdio_client(params))
                session = await self._stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self._sessions[server] = session
                listed = await session.list_tools()
                for t in listed.tools:
                    self._tools.append(MCPTool(
                        self, server, t.name, t.description or "",
                        getattr(t, "inputSchema", None) or {"type": "object", "properties": {}},
                    ))
                notes.append(f"已连接 MCP '{server}': {len(listed.tools)} 个工具")
            except Exception as exc:  # noqa: BLE001
                notes.append(f"连接 MCP '{server}' 失败: {exc}")
        return notes

    async def call_tool(self, server: str, name: str, arguments: dict[str, Any]) -> ToolResult:
        session = self._sessions.get(server)
        if session is None:
            return ToolResult(content=f"MCP server '{server}' 未连接", is_error=True)
        try:
            result = await session.call_tool(name, arguments)
            parts: list[str] = []
            for block in getattr(result, "content", []) or []:
                text = getattr(block, "text", None)
                if text:
                    parts.append(text)
            content = "\n".join(parts) if parts else str(result)
            return ToolResult(content=content, is_error=bool(getattr(result, "isError", False)))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(content=f"MCP 调用失败: {exc}", is_error=True)

    def tools(self) -> list[MCPTool]:
        return list(self._tools)

    async def aclose(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
        self._sessions.clear()
        self._tools.clear()
