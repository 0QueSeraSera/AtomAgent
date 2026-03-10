"""Persistence helpers for proactive runtime state."""

from __future__ import annotations

import json
from pathlib import Path

from atom_agent.proactive.models import ProactiveRuntimeState

STATE_DIRNAME = ".proactive"
STATE_FILENAME = "state.json"


def get_state_dir(workspace: Path) -> Path:
    """Return runtime state directory under the workspace."""
    return workspace / STATE_DIRNAME


def get_state_path(workspace: Path) -> Path:
    """Return runtime state file path under the workspace."""
    return get_state_dir(workspace) / STATE_FILENAME


def load_runtime_state(workspace: Path) -> ProactiveRuntimeState:
    """Load runtime state from workspace; return empty state if missing or invalid."""
    path = get_state_path(workspace)
    if not path.exists():
        return ProactiveRuntimeState()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ProactiveRuntimeState()

    if not isinstance(raw, dict):
        return ProactiveRuntimeState()

    try:
        return ProactiveRuntimeState.from_dict(raw)
    except (KeyError, TypeError, ValueError):
        return ProactiveRuntimeState()


def save_runtime_state(workspace: Path, state: ProactiveRuntimeState) -> Path:
    """Persist runtime state atomically and return output path."""
    state_dir = get_state_dir(workspace)
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / STATE_FILENAME
    tmp_path = state_dir / f"{STATE_FILENAME}.tmp"
    tmp_path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return path
