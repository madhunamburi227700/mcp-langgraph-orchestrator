import asyncio
import logging
from typing import Any, Optional
from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters
from mcp.types import Tool, CallToolResult

logging.basicConfig(level=logging.INFO)

class MCPToolExecutor:
    def __init__(self, name: str = "code-search", command: str = "python", args: Optional[list[str]] = None) -> None:
        if args is None:
            args = ["mcp_server/server.py"]
        self.name = name
        self.command = command
        self.args = args
        self.session: ClientSession | None = None
        self.exit_stack = None

    async def initialize(self) -> None:
        from contextlib import AsyncExitStack
        self.exit_stack = AsyncExitStack()
        await self.exit_stack.__aenter__()
        try:
            read, write = await self.exit_stack.enter_async_context(stdio_client(StdioServerParameters(
                command=self.command, args=self.args
            )))
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.session = session
            logging.info(f"Initialized MCP Tool Executor: {self.name}")
        except Exception as e:
            logging.error(f"Failed to initialize MCPToolExecutor '{self.name}': {e}")
            raise

    async def list_tools(self) -> list[Tool]:
        assert self.session is not None
        tools_response = await self.session.list_tools()
        tools = []
        for item in tools_response:
            if isinstance(item, tuple) and item[0] == "tools":
                tools.extend([Tool(**tool) if isinstance(tool, dict) else tool for tool in item[1]])
        return tools

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> CallToolResult:
        assert self.session is not None
        return await self.session.call_tool(tool_name, arguments)

    async def cleanup(self) -> None:
        if self.exit_stack:
            await self.exit_stack.aclose()