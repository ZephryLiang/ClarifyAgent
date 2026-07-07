"""MCP client for consuming external job-platform tool servers."""

from .client import MCPManager, MCPTool, load_mcp_config

__all__ = ["MCPManager", "MCPTool", "load_mcp_config"]
