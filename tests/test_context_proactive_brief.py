"""Tests for proactive brief injection in ContextBuilder system prompt."""

from __future__ import annotations

import textwrap

from atom_agent.agent.context import ContextBuilder
from atom_agent.workspace import WorkspaceManager


def test_context_includes_proactive_brief_for_valid_config(tmp_path) -> None:
    workspace = tmp_path / "ctx-valid"
    WorkspaceManager(workspace).init_workspace(name="ctx-valid")

    (workspace / "PROACTIVE.md").write_text(
        textwrap.dedent(
            """
            # Proactive Configuration

            ```json
            {
              "version": 1,
              "enabled": true,
              "timezone": "UTC",
              "tasks": [
                {
                  "id": "daily-checkin",
                  "kind": "cron",
                  "cron": "0 10 * * *",
                  "session_key": "cli:123",
                  "prompt": "Send a check-in."
                }
              ]
            }
            ```
            """
        ).strip(),
        encoding="utf-8",
    )

    prompt = ContextBuilder(workspace).build_system_prompt()
    assert "## PROACTIVE.md (brief)" in prompt
    assert "active_tasks: 1 / 1" in prompt
    assert "daily-checkin [cron] -> cli:123 (target: session_key route)" in prompt


def test_context_shows_warning_for_invalid_proactive_config(tmp_path) -> None:
    workspace = tmp_path / "ctx-invalid"
    WorkspaceManager(workspace).init_workspace(name="ctx-invalid")
    (workspace / "PROACTIVE.md").write_text("# Proactive\n\nNo JSON block.", encoding="utf-8")

    prompt = ContextBuilder(workspace).build_system_prompt()
    assert "## PROACTIVE.md (brief)" in prompt
    assert "WARNING: PROACTIVE.md is invalid" in prompt
    assert "[missing_json_block]" in prompt
