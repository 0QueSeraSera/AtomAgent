"""Tools for progressive memory retrieval (brief-first, read-on-demand)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from atom_agent.logging import get_logger
from atom_agent.memory import MemoryStore
from atom_agent.tools.base import Tool

logger = get_logger("tools.memory")

_SCOPES = {"all", "global", "project", "active_project"}


class MemorySearchTool(Tool):
    """Search memory files and return compact handles/snippets."""

    def __init__(
        self,
        workspace: Path,
        default_project_id: str | None = None,
        default_limit: int = 5,
    ):
        self._store = MemoryStore(workspace)
        self._default_project_id = default_project_id
        self._default_limit = default_limit

    @property
    def name(self) -> str:
        return "memory_search"

    @property
    def description(self) -> str:
        return (
            "Search global or project memory and return compact handles. "
            "Use memory_read(memory_id=...) to fetch full details."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query keywords."},
                "scope": {
                    "type": "string",
                    "enum": ["all", "global", "project", "active_project"],
                    "description": "Memory scope. active_project uses current workspace project id.",
                },
                "project_id": {
                    "type": "string",
                    "description": "Optional project id override for project scope.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        scope: str = "all",
        project_id: str | None = None,
        limit: int | None = None,
        **kwargs: Any,
    ) -> str:
        scope = scope if scope in _SCOPES else "all"
        effective_project = project_id or self._default_project_id
        if scope == "active_project":
            scope = "project"

        results = self._store.search(
            query=query,
            scope=scope,
            project_id=effective_project,
            limit=limit or self._default_limit,
        )

        payload = {
            "query": query,
            "scope": scope,
            "project_id": self._store.resolve_project_id(effective_project)
            if effective_project
            else None,
            "results": results,
            "hint": "Use memory_read with a memory_id from results for full content.",
        }
        logger.debug(
            "Memory search executed",
            extra={"scope": scope, "result_count": len(results)},
        )
        return json.dumps(payload, ensure_ascii=False, indent=2)


class MemoryReadTool(Tool):
    """Read one memory entry by handle."""

    def __init__(self, workspace: Path):
        self._store = MemoryStore(workspace)

    @property
    def name(self) -> str:
        return "memory_read"

    @property
    def description(self) -> str:
        return "Read a memory entry by memory_id returned by memory_search."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "memory_id": {"type": "string", "description": "Entry handle from memory_search."},
                "max_chars": {"type": "integer", "minimum": 200, "maximum": 50000},
            },
            "required": ["memory_id"],
        }

    async def execute(
        self,
        memory_id: str,
        max_chars: int = 8000,
        **kwargs: Any,
    ) -> str:
        entry = self._store.read_entry(memory_id, max_chars=max_chars)
        if entry is None:
            return json.dumps(
                {
                    "memory_id": memory_id,
                    "error": "Memory entry not found.",
                },
                ensure_ascii=False,
                indent=2,
            )
        return json.dumps(entry, ensure_ascii=False, indent=2)
