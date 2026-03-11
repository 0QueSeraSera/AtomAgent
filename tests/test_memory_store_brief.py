"""Tests for brief-first memory context behavior."""

from __future__ import annotations

from atom_agent.agent.context import ContextBuilder
from atom_agent.memory import MemoryStore
from atom_agent.workspace import WorkspaceManager


def test_memory_brief_includes_global_and_project_sections(tmp_path) -> None:
    workspace = tmp_path / "brief-ws"
    WorkspaceManager(workspace).init_workspace(name="brief-ws")
    store = MemoryStore(workspace)

    store.global_brief_file.write_text(
        "# Global Brief\n\n- user prefers concise replies\n- avoid broad refactors\n",
        encoding="utf-8",
    )
    project_dir = store.get_project_dir("repo-alpha")
    (project_dir / "BRIEF.md").write_text(
        "# Repo Alpha\n\n- pytest command: pytest tests/\n- style: ruff + black\n",
        encoding="utf-8",
    )

    brief = store.build_prompt_brief("repo-alpha")
    assert "## Global Memory Brief" in brief
    assert "user prefers concise replies" in brief
    assert "## Project Memory Brief (repo-alpha)" in brief
    assert "pytest command: pytest tests/" in brief


def test_memory_brief_falls_back_to_legacy_memory_file(tmp_path) -> None:
    workspace = tmp_path / "legacy-memory"
    WorkspaceManager(workspace).init_workspace(name="legacy-memory")
    store = MemoryStore(workspace)

    store.write_long_term(
        "# Long-term Memory\n\n- keep behavior stable\n- prioritize reliability over novelty\n"
    )
    brief = store.build_prompt_brief()
    assert "## Global Memory Brief" in brief
    assert "prioritize reliability over novelty" in brief


def test_context_builder_only_injects_project_brief(tmp_path) -> None:
    workspace = tmp_path / "ctx-project"
    WorkspaceManager(workspace).init_workspace(name="ctx-project")
    store = MemoryStore(workspace)

    store.global_brief_file.write_text("- global line", encoding="utf-8")
    project_dir = store.get_project_dir("demo-repo")
    (project_dir / "BRIEF.md").write_text("- project brief line", encoding="utf-8")
    (project_dir / "FACTS.md").write_text("- secret full facts should not auto-inject", encoding="utf-8")

    prompt = ContextBuilder(workspace).build_system_prompt(project_id="demo-repo")
    assert "project brief line" in prompt
    assert "secret full facts should not auto-inject" not in prompt
