"""Data models for workspace MCP configuration."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

MCPTransport = Literal["stdio", "sse", "streamableHttp"]


@dataclass(frozen=True)
class MCPValidationIssue:
    """Structured MCP config validation issue."""

    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Serialize issue to JSON-safe dictionary."""
        return {"code": self.code, "path": self.path, "message": self.message}


class MCPValidationError(ValueError):
    """Raised when MCP configuration parsing/validation fails."""

    def __init__(self, issues: list[MCPValidationIssue]):
        super().__init__("Invalid MCP configuration")
        self.issues = issues

    def __str__(self) -> str:
        joined = "; ".join(f"{item.path}: {item.message}" for item in self.issues)
        return f"Invalid MCP configuration: {joined}"


@dataclass
class MCPServerConfig:
    """One MCP server entry in `.mcp.json`."""

    name: str
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    type: MCPTransport | None = None
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    tool_timeout: float = 30.0

    @property
    def transport(self) -> MCPTransport:
        """Resolve effective transport when `type` is omitted."""
        if self.type:
            return self.type
        if self.command:
            return "stdio"
        if self.url:
            return "sse" if self.url.rstrip("/").endswith("/sse") else "streamableHttp"
        return "stdio"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dictionary."""
        return {
            "name": self.name,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "url": self.url,
            "type": self.type,
            "headers": self.headers,
            "enabled": self.enabled,
            "tool_timeout": self.tool_timeout,
            "transport": self.transport,
        }


@dataclass
class MCPConfig:
    """Normalized workspace MCP configuration."""

    servers: dict[str, MCPServerConfig] = field(default_factory=dict)
    source_path: Path | None = None

    @property
    def enabled_servers(self) -> list[MCPServerConfig]:
        """Return enabled server configs."""
        return [server for server in self.servers.values() if server.enabled]
