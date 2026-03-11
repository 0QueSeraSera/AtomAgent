"""MCP client manager for connecting servers and registering tool wrappers."""

from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from atom_agent.logging import get_logger
from atom_agent.mcp.config import load_workspace_mcp_config
from atom_agent.mcp.models import MCPConfig, MCPServerConfig
from atom_agent.tools.mcp import MCPTool
from atom_agent.tools.registry import ToolRegistry

logger = get_logger("mcp.client")


@dataclass
class MCPDiscoveredTool:
    """Normalized remote MCP tool descriptor."""

    name: str
    description: str
    input_schema: dict[str, Any]


class MCPClientManager:
    """Connect MCP servers and register wrapped tools into ToolRegistry."""

    def __init__(self, workspace: Path, registry: ToolRegistry):
        self.workspace = workspace
        self.registry = registry
        self._stack: AsyncExitStack | None = None
        self._registered_tool_names: list[str] = []
        self._connected_servers: list[str] = []

    @property
    def registered_tool_names(self) -> list[str]:
        """Return currently registered MCP tool names."""
        return list(self._registered_tool_names)

    @property
    def connected_servers(self) -> list[str]:
        """Return currently connected MCP server names."""
        return list(self._connected_servers)

    async def connect_from_workspace(self) -> list[str]:
        """Load workspace config and connect enabled MCP servers."""
        config = load_workspace_mcp_config(self.workspace)
        return await self.connect(config)

    async def connect(self, config: MCPConfig) -> list[str]:
        """Connect given MCP config and register tools."""
        await self.close()
        self._stack = AsyncExitStack()

        for server in config.enabled_servers:
            if server.transport != "stdio":
                logger.warning(
                    "Skipping unsupported MCP transport",
                    extra={"server": server.name, "transport": server.transport},
                )
                continue

            try:
                session = await self._open_server(server)
            except ImportError as err:
                logger.warning(
                    "MCP SDK not available; MCP disabled",
                    extra={"server": server.name, "error": str(err)},
                )
                continue
            except Exception as err:
                logger.error(
                    "Failed to connect MCP server",
                    extra={"server": server.name, "error": str(err)},
                )
                continue

            self._connected_servers.append(server.name)
            tools = await self._list_discovered_tools(session)
            for tool in tools:
                wrapper = MCPTool(
                    session=session,
                    server_name=server.name,
                    tool_name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema,
                    timeout=server.tool_timeout,
                )
                if self.registry.has(wrapper.name):
                    logger.warning(
                        "Skipping MCP tool due to name collision",
                        extra={"tool": wrapper.name, "server": server.name},
                    )
                    continue
                self.registry.register(wrapper)
                self._registered_tool_names.append(wrapper.name)

        return self.registered_tool_names

    async def close(self) -> None:
        """Unregister wrapped tools and close all MCP sessions."""
        for tool_name in self._registered_tool_names:
            self.registry.unregister(tool_name)
        self._registered_tool_names.clear()
        self._connected_servers.clear()

        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None

    async def _open_server(self, server: MCPServerConfig) -> Any:
        """Open one MCP server connection and return initialized session."""
        if self._stack is None:
            raise RuntimeError("MCP client stack is not initialized")
        return await self._open_stdio_session(server)

    async def _open_stdio_session(self, server: MCPServerConfig) -> Any:
        if not server.command:
            raise ValueError(f"MCP stdio server '{server.name}' missing command")

        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        assert self._stack is not None
        params = StdioServerParameters(
            command=server.command,
            args=server.args,
            env=server.env or None,
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return session

    async def _list_discovered_tools(self, session: Any) -> list[MCPDiscoveredTool]:
        """Normalize list_tools response into plain tool descriptors."""
        response = await session.list_tools()
        raw_tools = getattr(response, "tools", [])

        discovered: list[MCPDiscoveredTool] = []
        for item in raw_tools:
            name = _read_field(item, "name")
            if not isinstance(name, str) or not name.strip():
                continue
            description = _read_field(item, "description")
            if not isinstance(description, str):
                description = name
            input_schema = _read_field(item, "inputSchema")
            if not isinstance(input_schema, dict):
                input_schema = _read_field(item, "input_schema")
            if not isinstance(input_schema, dict):
                input_schema = {"type": "object", "properties": {}}
            discovered.append(
                MCPDiscoveredTool(
                    name=name,
                    description=description,
                    input_schema=input_schema,
                )
            )

        return discovered


def _read_field(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)
