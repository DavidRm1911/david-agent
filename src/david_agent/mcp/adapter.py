"""Wraps a single MCP tool as our Tool interface — same shape as
tools/filesystem.py etc. The Agent Loop calls .execute() the same way
whether a tool is native or came from MCP (CLAUDE.md §12).
"""

from __future__ import annotations

from david_agent.mcp.client import MCPClient
from david_agent.tools.base import Tool, ToolResult


class MCPToolAdapter(Tool):
    def __init__(self, client: MCPClient, server_name: str, mcp_tool_name: str, description: str) -> None:
        self.name = f"mcp.{server_name}.{mcp_tool_name}"
        self.description = description
        self.dangerous = True  # unknown external capability — default to cautious, unlike known-safe native tools
        self._client = client
        self._mcp_tool_name = mcp_tool_name

    def execute(self, args: dict) -> ToolResult:
        try:
            output = self._client.call_tool(self._mcp_tool_name, args)
        except Exception as e:  # noqa: BLE001 — surface any MCP/subprocess/timeout failure, never crash the loop
            return ToolResult(output="", error=str(e))
        return ToolResult(output=output)
