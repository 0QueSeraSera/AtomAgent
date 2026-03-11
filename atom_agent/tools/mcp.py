"""MCP-backed tool wrapper."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from atom_agent.logging import get_logger
from atom_agent.tools.base import Tool

logger = get_logger("tools.mcp")


def normalize_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Build a safe model-facing tool name for one MCP tool."""

    def _safe(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value).strip("_")
        return cleaned.lower() or "tool"

    return f"mcp_{_safe(server_name)}_{_safe(tool_name)}"


class MCPTool(Tool):
    """Wrap one remote MCP tool as a model-facing AtomAgent tool."""

    def __init__(
        self,
        *,
        session: Any,
        server_name: str,
        tool_name: str,
        description: str | None = None,
        input_schema: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ):
        self._session = session
        self._server_name = server_name
        self._tool_name = tool_name
        self._name = normalize_mcp_tool_name(server_name, tool_name)
        self._description = description or f"MCP tool `{tool_name}` from server `{server_name}`."
        self._parameters = input_schema or {"type": "object", "properties": {}}
        self._timeout = timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> str:
        try:
            result = await asyncio.wait_for(
                self._session.call_tool(self._tool_name, arguments=kwargs),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "MCP tool timeout",
                extra={"tool": self.name, "timeout": self._timeout},
            )
            return f"Error: MCP tool timed out after {self._timeout} seconds"
        except Exception as err:
            logger.error("MCP tool call failed", extra={"tool": self.name, "error": str(err)})
            return f"Error: MCP tool call failed - {err}"

        text = self._format_result(result)
        return text if text else "(no output)"

    @staticmethod
    def _format_result(result: Any) -> str:
        """Convert diverse MCP SDK result structures into plain text."""
        if result is None:
            return ""

        parts: list[str] = []
        content = getattr(result, "content", None)
        if isinstance(content, list):
            for block in content:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(block, dict):
                    parts.append(json.dumps(block, ensure_ascii=False))
                else:
                    dumped = getattr(block, "model_dump", None)
                    if callable(dumped):
                        parts.append(json.dumps(dumped(), ensure_ascii=False))
                    else:
                        parts.append(str(block))

        structured = getattr(result, "structuredContent", None)
        if structured:
            if isinstance(structured, (dict, list)):
                parts.append(json.dumps(structured, ensure_ascii=False))
            else:
                parts.append(str(structured))

        if parts:
            return "\n".join(part for part in parts if part)

        if isinstance(result, str):
            return result
        return str(result)
