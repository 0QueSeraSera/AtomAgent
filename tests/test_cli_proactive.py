"""CLI tests for proactive configuration commands."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path


def _run_cli(args: list[str], tmp_home: Path, cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    env.pop("ATOM_WORKSPACE", None)
    env.pop("ATOMAGENT_WORKSPACE", None)
    return subprocess.run(
        [sys.executable, "-m", "atom_agent", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_proactive_validate_succeeds_for_initialized_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "proactive-valid"
    home = tmp_path / "home"

    init = _run_cli(["init", str(workspace)], home, Path.cwd())
    assert init.returncode == 0, init.stderr

    result = _run_cli(["proactive", "validate", "--workspace", str(workspace)], home, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert "PROACTIVE config is valid" in result.stdout
    assert "Tasks: 0 total, 0 enabled" in result.stdout


def test_proactive_show_prints_task_summary(tmp_path: Path) -> None:
    workspace = tmp_path / "proactive-show"
    home = tmp_path / "home"

    init = _run_cli(["init", str(workspace)], home, Path.cwd())
    assert init.returncode == 0, init.stderr

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
                  "id": "wake-up",
                  "kind": "once",
                  "at": "2026-03-10T07:30:00+00:00",
                  "session_key": "telegram:123456",
                  "prompt": "Send a wake-up reminder."
                },
                {
                  "id": "daily-checkin",
                  "kind": "cron",
                  "cron": "0 10 * * *",
                  "jitter_sec": 900,
                  "session_key": "telegram:123456",
                  "prompt": "Send a short check-in."
                }
              ]
            }
            ```
            """
        ).strip(),
        encoding="utf-8",
    )

    result = _run_cli(["proactive", "show", "--workspace", str(workspace)], home, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert "Task Summary:" in result.stdout
    assert "wake-up [once]" in result.stdout
    assert "daily-checkin [cron]" in result.stdout
    assert "session_key: telegram:123456" in result.stdout


def test_proactive_validate_shows_structured_errors(tmp_path: Path) -> None:
    workspace = tmp_path / "proactive-invalid"
    home = tmp_path / "home"

    init = _run_cli(["init", str(workspace)], home, Path.cwd())
    assert init.returncode == 0, init.stderr

    (workspace / "PROACTIVE.md").write_text("# Proactive\n\nNo JSON config.", encoding="utf-8")

    result = _run_cli(["proactive", "validate", "--workspace", str(workspace)], home, Path.cwd())
    assert result.returncode == 1
    assert "PROACTIVE config invalid" in result.stderr
    assert "[missing_json_block]" in result.stderr
