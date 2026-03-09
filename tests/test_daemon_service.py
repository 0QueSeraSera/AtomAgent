"""Integration-style tests for daemon proactive dispatch."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from atom_agent.daemon import DaemonService
from atom_agent.proactive.state import load_runtime_state
from atom_agent.provider.base import LLMProvider, LLMResponse
from atom_agent.session import SessionManager
from atom_agent.workspace import WorkspaceManager


class DummyProvider(LLMProvider):
    """Minimal provider for daemon dispatch tests."""

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="proactive reply")

    def get_default_model(self) -> str:
        return "dummy-model"


def _write_proactive(path: Path, payload: str) -> None:
    path.write_text(
        textwrap.dedent(
            f"""
            # Proactive Configuration

            ```json
            {payload}
            ```
            """
        ).strip(),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_daemon_run_once_dispatches_due_once_task(tmp_path: Path) -> None:
    workspace = tmp_path / "daemon-ws"
    WorkspaceManager(workspace).init_workspace(name="daemon-ws")

    _write_proactive(
        workspace / "PROACTIVE.md",
        """{
  "version": 1,
  "enabled": true,
  "timezone": "UTC",
  "tasks": [
    {
      "id": "wake-up",
      "kind": "once",
      "at": "2026-03-01T08:00:00+00:00",
      "session_key": "cli:test-daemon",
      "prompt": "Send wake-up reminder."
    }
  ]
}""",
    )

    service = DaemonService(provider=DummyProvider(), workspace_paths=[workspace])
    reports = await service.run_once()
    assert len(reports) == 1
    assert reports[0].task_id == "wake-up"
    assert reports[0].status == "success"

    state = load_runtime_state(workspace)
    assert state.tasks["wake-up"].completed_at is not None

    session = SessionManager(workspace, workspace.name).get_or_create("cli:test-daemon")
    assert len(session.messages) > 0


@pytest.mark.asyncio
async def test_daemon_skips_invalid_workspace_config_and_continues(tmp_path: Path) -> None:
    valid_ws = tmp_path / "valid"
    invalid_ws = tmp_path / "invalid"
    WorkspaceManager(valid_ws).init_workspace(name="valid")
    WorkspaceManager(invalid_ws).init_workspace(name="invalid")

    _write_proactive(
        valid_ws / "PROACTIVE.md",
        """{
  "version": 1,
  "enabled": true,
  "timezone": "UTC",
  "tasks": [
    {
      "id": "ping",
      "kind": "once",
      "at": "2026-03-01T08:00:00+00:00",
      "session_key": "cli:ok",
      "prompt": "Ping."
    }
  ]
}""",
    )
    (invalid_ws / "PROACTIVE.md").write_text("# bad config", encoding="utf-8")

    service = DaemonService(provider=DummyProvider(), workspace_paths=[valid_ws, invalid_ws])
    reports = await service.run_once()

    assert len(reports) == 1
    assert reports[0].workspace == "valid"
    assert reports[0].status == "success"
