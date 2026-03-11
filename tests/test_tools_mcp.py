"""Tests for MCP tool wrapper behavior."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from atom_agent.tools.mcp import MCPTool, normalize_mcp_tool_name


@dataclass
class _TextBlock:
    text: str


@dataclass
class _CallResult:
    content: list
    structuredContent: dict | None = None


class _Session:
    async def call_tool(self, name: str, arguments: dict):
        return _CallResult(content=[_TextBlock(text=f"called {name} with {arguments['q']}")])


class _SlowSession:
    async def call_tool(self, name: str, arguments: dict):
        await asyncio.sleep(0.2)
        return _CallResult(content=[])


def test_normalize_mcp_tool_name() -> None:
    assert normalize_mcp_tool_name("Repo-Graph", "query.code") == "mcp_repo_graph_query_code"


async def test_mcp_tool_execute_returns_text_blocks() -> None:
    tool = MCPTool(
        session=_Session(),
        server_name="repo_graph",
        tool_name="query",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
    )
    result = await tool.execute(q="auth flow")
    assert "called query with auth flow" in result


async def test_mcp_tool_execute_timeout_returns_error() -> None:
    tool = MCPTool(
        session=_SlowSession(),
        server_name="repo_graph",
        tool_name="query",
        timeout=0.05,
    )
    result = await tool.execute(q="auth flow")
    assert result.startswith("Error: MCP tool timed out")
