"""Tests for progressive memory tools."""

from __future__ import annotations

import json

import pytest

from atom_agent.memory import MemoryStore
from atom_agent.tools.memory import MemoryReadTool, MemorySearchTool
from atom_agent.workspace import WorkspaceManager


def _prepare_workspace(tmp_path):
    workspace = tmp_path / "memory-tools"
    WorkspaceManager(workspace).init_workspace(name="memory-tools")
    store = MemoryStore(workspace)
    store.global_brief_file.write_text(
        "- user prefers short replies\n- prioritize test-first fixes\n",
        encoding="utf-8",
    )
    project_dir = store.get_project_dir("repo-a")
    (project_dir / "BRIEF.md").write_text("- project repo-a brief", encoding="utf-8")
    (project_dir / "FACTS.md").write_text(
        "- pytest command is PYTHONPATH=. pytest -p no:cacheprovider tests/\n",
        encoding="utf-8",
    )
    return workspace


@pytest.mark.asyncio
async def test_memory_search_returns_handles(tmp_path) -> None:
    workspace = _prepare_workspace(tmp_path)
    tool = MemorySearchTool(workspace=workspace, default_project_id="repo-a")

    raw = await tool.execute(query="pytest command", scope="project", limit=3)
    payload = json.loads(raw)
    assert payload["results"]
    assert payload["results"][0]["memory_id"].startswith("project:repo-a:")


@pytest.mark.asyncio
async def test_memory_read_returns_content(tmp_path) -> None:
    workspace = _prepare_workspace(tmp_path)
    search_tool = MemorySearchTool(workspace=workspace, default_project_id="repo-a")
    read_tool = MemoryReadTool(workspace=workspace)

    results = json.loads(await search_tool.execute(query="pytest", scope="project", limit=2))
    memory_id = results["results"][0]["memory_id"]
    detail = json.loads(await read_tool.execute(memory_id=memory_id))

    assert detail["memory_id"] == memory_id
    assert "pytest -p no:cacheprovider" in detail["content"]


@pytest.mark.asyncio
async def test_memory_read_handles_missing_entry(tmp_path) -> None:
    workspace = _prepare_workspace(tmp_path)
    read_tool = MemoryReadTool(workspace=workspace)

    detail = json.loads(await read_tool.execute(memory_id="project:repo-a:DOES_NOT_EXIST.md"))
    assert detail["error"] == "Memory entry not found."
