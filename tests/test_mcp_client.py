"""Tests for MCP client manager registration bridge."""

from __future__ import annotations

from dataclasses import dataclass

from atom_agent.mcp import MCPClientManager, MCPConfig, MCPServerConfig
from atom_agent.tools.registry import ToolRegistry


@dataclass
class _RemoteTool:
    name: str
    description: str
    inputSchema: dict


@dataclass
class _ListToolsResponse:
    tools: list[_RemoteTool]


@dataclass
class _TextBlock:
    text: str


@dataclass
class _CallResult:
    content: list


class _FakeSession:
    async def list_tools(self):
        return _ListToolsResponse(
            tools=[
                _RemoteTool(
                    name="query",
                    description="Search code graph",
                    inputSchema={"type": "object", "properties": {"q": {"type": "string"}}},
                )
            ]
        )

    async def call_tool(self, name: str, arguments: dict):
        return _CallResult(content=[_TextBlock(text=f"{name}:{arguments['q']}")])


async def test_mcp_client_registers_wrapped_tools_and_can_execute(tmp_path) -> None:
    registry = ToolRegistry()
    manager = MCPClientManager(workspace=tmp_path, registry=registry)

    async def _fake_open_server(server):
        return _FakeSession()

    manager._open_server = _fake_open_server  # type: ignore[method-assign]
    config = MCPConfig(
        servers={
            "repo_graph": MCPServerConfig(name="repo_graph", command="npx", args=["fake", "mcp"])
        }
    )
    names = await manager.connect(config)
    assert "mcp_repo_graph_query" in names
    assert registry.has("mcp_repo_graph_query")

    result = await registry.execute("mcp_repo_graph_query", {"q": "auth"})
    assert result == "query:auth"

    await manager.close()
    assert not registry.has("mcp_repo_graph_query")


async def test_mcp_client_skips_non_stdio_transports(tmp_path) -> None:
    registry = ToolRegistry()
    manager = MCPClientManager(workspace=tmp_path, registry=registry)
    config = MCPConfig(
        servers={"remote": MCPServerConfig(name="remote", url="https://example.com/mcp/sse")}
    )
    names = await manager.connect(config)
    assert names == []
    assert manager.connected_servers == []
