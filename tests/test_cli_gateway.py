"""CLI tests for gateway command."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _run_cli(
    args: list[str],
    tmp_home: Path,
    cwd: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["HOME"] = str(tmp_home)
    env["DEEPSEEK_API_KEY"] = "test-key"
    env.pop("ATOM_WORKSPACE", None)
    env.pop("ATOMAGENT_WORKSPACE", None)
    for key in [
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_VERIFICATION_TOKEN",
        "FEISHU_SIGNING_SECRET",
    ]:
        env.pop(key, None)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, "-m", "atom_agent", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_gateway_once_fails_without_feishu_credentials(tmp_path: Path) -> None:
    workspace = tmp_path / "gw-missing-creds"
    home = tmp_path / "home"

    init = _run_cli(["init", str(workspace)], home, Path.cwd())
    assert init.returncode == 0, init.stderr

    result = _run_cli(
        ["gateway", "run", "--once", "--workspace", str(workspace)],
        home,
        Path.cwd(),
    )
    assert result.returncode == 1
    assert "Feishu adapter is not ready" in result.stderr
    assert "FEISHU_APP_ID" in result.stderr


def test_gateway_once_succeeds_with_feishu_credentials(tmp_path: Path) -> None:
    workspace = tmp_path / "gw-ready"
    home = tmp_path / "home"

    init = _run_cli(["init", str(workspace)], home, Path.cwd())
    assert init.returncode == 0, init.stderr

    result = _run_cli(
        ["gateway", "run", "--once", "--workspace", str(workspace)],
        home,
        Path.cwd(),
        extra_env={
            "FEISHU_APP_ID": "cli_demo",
            "FEISHU_APP_SECRET": "sec_demo",
            "FEISHU_VERIFICATION_TOKEN": "verify-demo",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "Feishu readiness:" in result.stdout
    assert "Starting gateway once for readiness check" in result.stdout

