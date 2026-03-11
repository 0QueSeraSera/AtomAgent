"""Tests for MCP config parsing and workspace loading."""

from __future__ import annotations

import textwrap

import pytest

from atom_agent.mcp import MCPValidationError, load_workspace_mcp_config, parse_mcp_json


def test_load_workspace_mcp_config_missing_file_returns_empty(tmp_path) -> None:
    config = load_workspace_mcp_config(tmp_path)
    assert config.servers == {}
    assert config.source_path == tmp_path / ".mcp.json"


def test_parse_mcp_json_valid_stdio_server() -> None:
    config = parse_mcp_json(
        textwrap.dedent(
            """
            {
              "mcpServers": {
                "repo_graph": {
                  "command": "npx",
                  "args": ["-y", "repo-graph-mcp", "serve"],
                  "env": {"TOKEN": "abc"},
                  "tool_timeout": 45
                }
              }
            }
            """
        ).strip()
    )
    server = config.servers["repo_graph"]
    assert server.transport == "stdio"
    assert server.command == "npx"
    assert server.args == ["-y", "repo-graph-mcp", "serve"]
    assert server.env == {"TOKEN": "abc"}
    assert server.enabled is True
    assert server.tool_timeout == 45.0


def test_parse_mcp_json_infers_url_transport() -> None:
    config = parse_mcp_json(
        '{"mcpServers":{"remote":{"url":"https://example.com/mcp/sse","enabled":true}}}'
    )
    assert config.servers["remote"].transport == "sse"


def test_parse_mcp_json_raises_for_invalid_shape() -> None:
    with pytest.raises(MCPValidationError) as exc:
        parse_mcp_json('{"mcpServers":{"bad":{"args":"not-an-array"}}}')
    errors = [(issue.code, issue.path) for issue in exc.value.issues]
    assert ("invalid_type", "mcpServers.bad.args") in errors


def test_load_workspace_mcp_config_non_strict_ignores_invalid_file(tmp_path) -> None:
    (tmp_path / ".mcp.json").write_text('{"mcpServers":{"bad":{"args":"oops"}}}', encoding="utf-8")
    config = load_workspace_mcp_config(tmp_path, strict=False)
    assert config.servers == {}


def test_load_workspace_mcp_config_strict_surfaces_invalid_file(tmp_path) -> None:
    (tmp_path / ".mcp.json").write_text('{"mcpServers":{"bad":{"args":"oops"}}}', encoding="utf-8")
    with pytest.raises(MCPValidationError):
        load_workspace_mcp_config(tmp_path, strict=True)
