"""Tests for workspace/session management CLI behavior."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from atom_agent.session.manager import SessionManager
from atom_agent.workspace import BOOTSTRAP_FILES


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


def test_init_creates_default_context_files_with_content(tmp_path: Path) -> None:
    """`init` should create all context files with default template content."""
    workspace = tmp_path / "init-workspace"
    result = _run_cli(["init", str(workspace)], tmp_path / "home", Path.cwd())

    assert result.returncode == 0, result.stderr
    for filename in BOOTSTRAP_FILES:
        path = workspace / filename
        assert path.exists(), f"Missing {filename}"
        assert path.read_text(encoding="utf-8").strip(), f"{filename} should not be empty"

    memory = workspace / "memory" / "MEMORY.md"
    history = workspace / "memory" / "HISTORY.md"
    assert memory.exists() and memory.read_text(encoding="utf-8").strip()
    assert history.exists() and history.read_text(encoding="utf-8").strip()


def test_session_list_auto_initializes_workspace(tmp_path: Path) -> None:
    """Session list should initialize missing workspace context instead of hard-failing."""
    workspace = tmp_path / "ws2"
    workspace.mkdir(parents=True)

    result = _run_cli(
        ["session", "--workspace", str(workspace), "list"],
        tmp_path / "home",
        Path.cwd(),
    )

    assert result.returncode == 0, result.stderr
    assert "Initialized workspace context files" in result.stdout
    assert "No sessions found." in result.stdout

    for filename in BOOTSTRAP_FILES:
        assert (workspace / filename).exists(), f"Missing {filename} after auto-init"


def test_workspace_overview_includes_session_counts(tmp_path: Path) -> None:
    """Workspace overview should show a clear workspace/session table."""
    workspace = tmp_path / "alpha-ws"
    home = tmp_path / "home"

    create = _run_cli(
        ["workspace", "create", "alpha", "--path", str(workspace)],
        home,
        Path.cwd(),
    )
    assert create.returncode == 0, create.stderr

    manager = SessionManager(workspace, "alpha")
    session = manager.get_or_create("cli:test")
    session.add_message("user", "hello")
    manager.save(session)

    overview = _run_cli(["workspace", "overview"], home, Path.cwd())
    assert overview.returncode == 0, overview.stderr
    assert "Workspaces" in overview.stdout
    assert "alpha" in overview.stdout
    assert re.search(r"alpha\s+valid\s+1", overview.stdout), overview.stdout


def test_tui_once_prints_workspace_dashboard(tmp_path: Path) -> None:
    """`tui --once` should render dashboard without interactive input."""
    workspace = tmp_path / "beta-ws"
    home = tmp_path / "home"

    create = _run_cli(
        ["workspace", "create", "beta", "--path", str(workspace)],
        home,
        Path.cwd(),
    )
    assert create.returncode == 0, create.stderr

    result = _run_cli(["tui", "--once"], home, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert "Workspaces" in result.stdout
    assert "beta" in result.stdout
    assert "Commands:" in result.stdout


def test_workspace_overview_uses_atom_agents_home(tmp_path: Path) -> None:
    """Default workspace root should live under ~/.atom-agents."""
    home = tmp_path / "home"

    result = _run_cli(["workspace", "overview"], home, Path.cwd())
    assert result.returncode == 0, result.stderr
    assert str(home / ".atom-agents" / "workspaces" / "default") in result.stdout
