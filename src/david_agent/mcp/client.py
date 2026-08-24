"""A short-lived connection per operation: list_tools() and call_tool() each
spawn the server process, do the one operation, and close. Simpler than
keeping a persistent async session alive underneath a synchronous Agent
Loop, at the cost of paying process startup again on every call — an honest
trade-off for a first working version, not a permanent design choice.
"""

from __future__ import annotations

import asyncio

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool as MCPToolSpec

from david_agent.mcp.registry import MCPServerConfig


class MCPClient:
    def __init__(self, config: MCPServerConfig, *, timeout: float = 20.0) -> None:
        self._config = config
        self._timeout = timeout

    def list_tools(self) -> list[MCPToolSpec]:
        return asyncio.run(asyncio.wait_for(self._list_tools(), timeout=self._timeout))

    def call_tool(self, name: str, arguments: dict) -> str:
        return asyncio.run(asyncio.wait_for(self._call_tool(name, arguments), timeout=self._timeout))

    def _params(self) -> StdioServerParameters:
        return StdioServerParameters(command=self._config.command, args=self._config.args, env=self._config.env)

    async def _list_tools(self) -> list[MCPToolSpec]:
        async with stdio_client(self._params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.list_tools()
                return result.tools

    async def _call_tool(self, name: str, arguments: dict) -> str:
        async with stdio_client(self._params()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                parts = [getattr(block, "text", None) or str(block) for block in result.content]
                return "\n".join(parts) if parts else "(no output)"
