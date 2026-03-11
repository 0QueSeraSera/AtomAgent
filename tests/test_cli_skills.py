"""Tests for skill management CLI behavior."""

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


def test_skill_install_list_and_show(tmp_path: Path) -> None:
    workspace = tmp_path / "skills-ws"
    home = tmp_path / "home"
    source = tmp_path / "repo-map"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        textwrap.dedent(
            """
            ---
            description: "Map repository layout."
            ---

            # Repo Map

            Use this skill to explore source trees.
            """
        ).strip(),
        encoding="utf-8",
    )
    (source / "notes.txt").write_text("asset", encoding="utf-8")

    install = _run_cli(
        ["skill", "install", str(source), "--workspace", str(workspace)],
        home,
        Path.cwd(),
    )
    assert install.returncode == 0, install.stderr
    assert (workspace / "skills" / "repo-map" / "SKILL.md").exists()
    assert (workspace / "skills" / "repo-map" / "notes.txt").exists()

    listed = _run_cli(["skill", "list", "--workspace", str(workspace)], home, Path.cwd())
    assert listed.returncode == 0, listed.stderr
    assert "repo-map [enabled]" in listed.stdout
    assert "Map repository layout." in listed.stdout

    shown = _run_cli(["skill", "show", "repo-map", "--workspace", str(workspace)], home, Path.cwd())
    assert shown.returncode == 0, shown.stderr
    assert "Skill: repo-map" in shown.stdout
    assert "# Repo Map" in shown.stdout
    assert "description:" not in shown.stdout


def test_skill_disable_then_enable(tmp_path: Path) -> None:
    workspace = tmp_path / "skills-toggle"
    home = tmp_path / "home"
    source = tmp_path / "triage"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("# Triage\n", encoding="utf-8")

    install = _run_cli(
        ["skill", "install", str(source), "--workspace", str(workspace)],
        home,
        Path.cwd(),
    )
    assert install.returncode == 0, install.stderr

    disable = _run_cli(["skill", "disable", "triage", "--workspace", str(workspace)], home, Path.cwd())
    assert disable.returncode == 0, disable.stderr

    listed_disabled = _run_cli(["skill", "list", "--workspace", str(workspace)], home, Path.cwd())
    assert listed_disabled.returncode == 0, listed_disabled.stderr
    assert "triage [disabled]" in listed_disabled.stdout

    enable = _run_cli(["skill", "enable", "triage", "--workspace", str(workspace)], home, Path.cwd())
    assert enable.returncode == 0, enable.stderr

    listed_enabled = _run_cli(["skill", "list", "--workspace", str(workspace)], home, Path.cwd())
    assert listed_enabled.returncode == 0, listed_enabled.stderr
    assert "triage [enabled]" in listed_enabled.stdout


def test_skill_install_from_skill_file_with_name_override(tmp_path: Path) -> None:
    workspace = tmp_path / "skills-file"
    home = tmp_path / "home"
    source_dir = tmp_path / "source-dir"
    source_dir.mkdir(parents=True)
    (source_dir / "SKILL.md").write_text("# Only File\n", encoding="utf-8")
    (source_dir / "asset.txt").write_text("ignore me", encoding="utf-8")

    result = _run_cli(
        [
            "skill",
            "install",
            str(source_dir / "SKILL.md"),
            "--workspace",
            str(workspace),
            "--name",
            "file-skill",
        ],
        home,
        Path.cwd(),
    )
    assert result.returncode == 0, result.stderr
    assert (workspace / "skills" / "file-skill" / "SKILL.md").exists()
    assert not (workspace / "skills" / "file-skill" / "asset.txt").exists()
