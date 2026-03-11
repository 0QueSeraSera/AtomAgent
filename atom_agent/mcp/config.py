"""Parser and loader for workspace `.mcp.json`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atom_agent.mcp.models import MCPConfig, MCPServerConfig, MCPValidationError, MCPValidationIssue

DEFAULT_MCP_FILENAME = ".mcp.json"
_TRANSPORTS = {"stdio", "sse", "streamableHttp"}


def load_workspace_mcp_config(
    workspace: Path,
    *,
    filename: str = DEFAULT_MCP_FILENAME,
    strict: bool = False,
) -> MCPConfig:
    """Load workspace `.mcp.json`; return empty config when absent/invalid unless strict."""
    source_path = workspace / filename
    if not source_path.exists():
        return MCPConfig(source_path=source_path)

    try:
        return parse_mcp_json(source_path.read_text(encoding="utf-8"), source_path=source_path)
    except MCPValidationError:
        if strict:
            raise
        return MCPConfig(source_path=source_path)


def parse_mcp_json(raw: str, *, source_path: Path | None = None) -> MCPConfig:
    """Parse and validate MCP JSON string."""
    data = _decode_json(raw)
    return _validate_config(data, source_path=source_path)


def _decode_json(raw: str) -> dict[str, Any]:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MCPValidationError(
            [
                MCPValidationIssue(
                    code="invalid_json",
                    path=f"json:{exc.lineno}:{exc.colno}",
                    message=exc.msg,
                )
            ]
        ) from exc
    if not isinstance(decoded, dict):
        raise MCPValidationError(
            [
                MCPValidationIssue(
                    code="invalid_root_type",
                    path="json",
                    message="Top-level JSON must be an object.",
                )
            ]
        )
    return decoded


def _validate_config(data: dict[str, Any], *, source_path: Path | None) -> MCPConfig:
    issues: list[MCPValidationIssue] = []
    servers_raw = data.get("mcpServers", {})
    if not isinstance(servers_raw, dict):
        issues.append(
            MCPValidationIssue(
                code="invalid_type",
                path="mcpServers",
                message="Expected object mapping server names to config objects.",
            )
        )
        raise MCPValidationError(issues)

    servers: dict[str, MCPServerConfig] = {}
    for name, raw_server in servers_raw.items():
        server_path = f"mcpServers.{name}"
        if not isinstance(name, str) or not name.strip():
            issues.append(
                MCPValidationIssue(
                    code="invalid_server_name",
                    path=server_path,
                    message="Server key must be a non-empty string.",
                )
            )
            continue
        if not isinstance(raw_server, dict):
            issues.append(
                MCPValidationIssue(
                    code="invalid_type",
                    path=server_path,
                    message="Server config must be an object.",
                )
            )
            continue

        server, server_issues = _validate_server(name=name, data=raw_server, path=server_path)
        if server_issues:
            issues.extend(server_issues)
            continue
        servers[name] = server

    if issues:
        raise MCPValidationError(issues)

    return MCPConfig(servers=servers, source_path=source_path)


def _validate_server(
    *,
    name: str,
    data: dict[str, Any],
    path: str,
) -> tuple[MCPServerConfig | None, list[MCPValidationIssue]]:
    issues: list[MCPValidationIssue] = []

    command = data.get("command")
    if command is not None and not isinstance(command, str):
        issues.append(_issue("invalid_type", f"{path}.command", "Expected string."))
        command = None

    args = data.get("args", [])
    if not isinstance(args, list) or not all(isinstance(item, str) for item in args):
        issues.append(_issue("invalid_type", f"{path}.args", "Expected array of strings."))
        args = []

    env = data.get("env", {})
    if not isinstance(env, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in env.items()
    ):
        issues.append(_issue("invalid_type", f"{path}.env", "Expected object of string values."))
        env = {}

    url = data.get("url")
    if url is not None and not isinstance(url, str):
        issues.append(_issue("invalid_type", f"{path}.url", "Expected string."))
        url = None

    transport = data.get("type")
    if transport is not None:
        if not isinstance(transport, str) or transport not in _TRANSPORTS:
            issues.append(
                _issue(
                    "invalid_transport",
                    f"{path}.type",
                    f"Expected one of: {sorted(_TRANSPORTS)}",
                )
            )
            transport = None

    headers = data.get("headers", {})
    if not isinstance(headers, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in headers.items()
    ):
        issues.append(
            _issue("invalid_type", f"{path}.headers", "Expected object of string values.")
        )
        headers = {}

    enabled = data.get("enabled", True)
    if not isinstance(enabled, bool):
        issues.append(_issue("invalid_type", f"{path}.enabled", "Expected boolean."))
        enabled = True

    tool_timeout = data.get("tool_timeout", 30.0)
    if isinstance(tool_timeout, int):
        tool_timeout = float(tool_timeout)
    if not isinstance(tool_timeout, float) or tool_timeout <= 0:
        issues.append(_issue("invalid_type", f"{path}.tool_timeout", "Expected number > 0."))
        tool_timeout = 30.0

    inferred_transport: str | None = transport
    if inferred_transport is None:
        if command:
            inferred_transport = "stdio"
        elif url:
            inferred_transport = "sse" if url.rstrip("/").endswith("/sse") else "streamableHttp"

    if inferred_transport == "stdio" and not command:
        issues.append(_issue("missing_field", f"{path}.command", "Required for stdio transport."))
    if inferred_transport in {"sse", "streamableHttp"} and not url:
        issues.append(_issue("missing_field", f"{path}.url", "Required for URL transports."))

    if issues:
        return None, issues

    return (
        MCPServerConfig(
            name=name,
            command=command,
            args=args,
            env=env,
            url=url,
            type=transport,
            headers=headers,
            enabled=enabled,
            tool_timeout=tool_timeout,
        ),
        [],
    )


def _issue(code: str, path: str, message: str) -> MCPValidationIssue:
    return MCPValidationIssue(code=code, path=path, message=message)
