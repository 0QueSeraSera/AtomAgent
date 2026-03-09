"""Workspace and session management helpers for CLI and TUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from atom_agent.config import ConfigManager
from atom_agent.workspace import BOOTSTRAP_FILES, WorkspaceManager


@dataclass
class WorkspaceSnapshot:
    """Workspace summary row for management views."""

    name: str
    path: Path
    active: bool
    registered: bool
    valid: bool
    errors: list[str]
    sessions: list[dict]

    @property
    def session_count(self) -> int:
        return len(self.sessions)


def ensure_workspace_initialized(path: Path, *, name: str | None = None) -> tuple[bool, list[str]]:
    """
    Ensure a workspace has required context files and directories.

    Returns:
        (did_initialize, remaining_errors)
    """
    manager = WorkspaceManager(path)
    errors = manager.validate_workspace(path)
    if not errors:
        return False, []

    manager.init_workspace(path, force=False, name=name or path.name)
    return True, manager.validate_workspace(path)


def collect_workspace_snapshots(
    config_manager: ConfigManager | None = None,
    *,
    include_paths: list[Path] | None = None,
) -> list[WorkspaceSnapshot]:
    """Collect workspace + session metadata for overview screens."""
    config = config_manager or ConfigManager()
    active_name = config.config.active_workspace
    include_paths = include_paths or []

    snapshots: list[WorkspaceSnapshot] = []
    seen_paths: set[Path] = set()

    for entry in config.list_workspaces():
        path = entry.path.expanduser().resolve()
        seen_paths.add(path)
        manager = WorkspaceManager(path)
        errors = manager.validate_workspace(path)
        sessions = manager.list_sessions(path)
        snapshots.append(
            WorkspaceSnapshot(
                name=entry.name,
                path=path,
                active=(entry.name == active_name),
                registered=True,
                valid=not errors,
                errors=errors,
                sessions=sessions,
            )
        )

    for extra in include_paths:
        path = extra.expanduser().resolve()
        if path in seen_paths:
            continue
        manager = WorkspaceManager(path)
        errors = manager.validate_workspace(path)
        sessions = manager.list_sessions(path)
        snapshots.append(
            WorkspaceSnapshot(
                name=path.name or str(path),
                path=path,
                active=False,
                registered=False,
                valid=not errors,
                errors=errors,
                sessions=sessions,
            )
        )

    snapshots.sort(key=lambda s: (not s.active, s.name.lower()))
    return snapshots


def format_workspace_overview(snapshots: list[WorkspaceSnapshot]) -> str:
    """Render a plain-text workspace overview table."""
    if not snapshots:
        return "No workspaces found."

    lines = []
    lines.append("Workspaces")
    lines.append("=" * 100)
    lines.append(
        f"{'#':>2}  {'Workspace':<20} {'Status':<10} {'Sessions':>8}  {'Registration':<13} Path"
    )
    lines.append("-" * 100)

    for idx, snap in enumerate(snapshots, start=1):
        marker = "*" if snap.active else " "
        status = "valid" if snap.valid else "invalid"
        reg = "registered" if snap.registered else "unregistered"
        lines.append(
            f"{idx:>2}{marker} {snap.name:<20} {status:<10} {snap.session_count:>8}  {reg:<13} {snap.path}"
        )

    lines.append("-" * 100)
    lines.append("* = active workspace")
    lines.append("Commands: open <#> | switch <#> | init <#> | create <name> [path] | help | quit")
    return "\n".join(lines)


def format_workspace_details(snapshot: WorkspaceSnapshot) -> str:
    """Render detailed info for one workspace."""
    lines = []
    lines.append(f"Workspace: {snapshot.name}")
    lines.append(f"Path: {snapshot.path}")
    lines.append(f"Registered: {'yes' if snapshot.registered else 'no'}")
    lines.append(f"Status: {'valid' if snapshot.valid else 'invalid'}")
    if snapshot.errors:
        lines.append("Errors:")
        for err in snapshot.errors:
            lines.append(f"  - {err}")

    lines.append("\nContext files:")
    for filename in BOOTSTRAP_FILES:
        status = "✓" if (snapshot.path / filename).exists() else "✗"
        lines.append(f"  {status} {filename}")

    lines.append("\nSessions:")
    if not snapshot.sessions:
        lines.append("  (none)")
    else:
        for session in snapshot.sessions:
            lines.append(
                f"  - {session.get('key', 'unknown')} | updated: {session.get('updated_at', 'unknown')}"
            )

    return "\n".join(lines)


class WorkspaceSessionTUI:
    """Simple interactive terminal UI for workspace/session management."""

    def __init__(self, *, include_paths: list[Path] | None = None):
        self._include_paths = include_paths or []
        self._config = ConfigManager()

    def run(self, *, once: bool = False) -> int:
        """Run interactive loop. With once=True, print dashboard and exit."""
        if once:
            print(self._render_dashboard())
            return 0

        print("AtomAgent Workspace & Session Manager")
        print("Type 'help' to see commands.\n")

        while True:
            print(self._render_dashboard())
            try:
                raw = input("\nmanager> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return 0
            if not raw:
                continue
            cmd, *rest = raw.split()
            cmd = cmd.lower()

            if cmd in {"q", "quit", "exit"}:
                return 0
            if cmd in {"h", "help"}:
                self._print_help()
                continue
            if cmd in {"r", "refresh"}:
                continue
            if cmd in {"open", "o"}:
                self._cmd_open(rest)
                continue
            if cmd in {"switch", "s"}:
                self._cmd_switch(rest)
                continue
            if cmd in {"init", "i"}:
                self._cmd_init(rest)
                continue
            if cmd in {"create", "c"}:
                self._cmd_create(rest)
                continue
            print("Unknown command. Type 'help'.")

    def _snapshots(self) -> list[WorkspaceSnapshot]:
        return collect_workspace_snapshots(self._config, include_paths=self._include_paths)

    def _render_dashboard(self) -> str:
        return format_workspace_overview(self._snapshots())

    def _pick_snapshot(self, index_text: str) -> WorkspaceSnapshot | None:
        try:
            idx = int(index_text)
        except ValueError:
            print("Index must be a number.")
            return None

        snapshots = self._snapshots()
        if idx < 1 or idx > len(snapshots):
            print("Invalid index.")
            return None
        return snapshots[idx - 1]

    def _cmd_open(self, args: list[str]) -> None:
        if not args:
            print("Usage: open <index>")
            return
        snap = self._pick_snapshot(args[0])
        if not snap:
            return
        print()
        print(format_workspace_details(snap))

    def _cmd_switch(self, args: list[str]) -> None:
        if not args:
            print("Usage: switch <index>")
            return
        snap = self._pick_snapshot(args[0])
        if not snap:
            return
        if not snap.registered:
            print("Can only switch to a registered workspace.")
            return
        if self._config.set_active_workspace(snap.name):
            print(f"Active workspace set to: {snap.name}")
        else:
            print(f"Failed to switch to workspace: {snap.name}")

    def _cmd_init(self, args: list[str]) -> None:
        if not args:
            print("Usage: init <index>")
            return
        snap = self._pick_snapshot(args[0])
        if not snap:
            return
        initialized, errors = ensure_workspace_initialized(snap.path, name=snap.name)
        if errors:
            print(f"Workspace still invalid: {errors[0]}")
            return
        if initialized:
            print(f"Initialized missing context files for: {snap.path}")
        else:
            print("Workspace already valid.")

    def _cmd_create(self, args: list[str]) -> None:
        if not args:
            print("Usage: create <name> [path]")
            return
        name = args[0]
        path = Path(args[1]).expanduser() if len(args) > 1 else None
        from atom_agent.config import WorkspaceRegistry

        entry = WorkspaceRegistry(self._config).create_workspace(name, path)
        print(f"Created workspace '{entry.name}' at {entry.path}")

    @staticmethod
    def _print_help() -> None:
        print(
            "\nCommands:\n"
            "  open <index>    Show workspace details and sessions\n"
            "  switch <index>  Set active workspace (registered only)\n"
            "  init <index>    Initialize/repair workspace files\n"
            "  create <name> [path]  Create and register workspace\n"
            "  refresh         Refresh dashboard\n"
            "  quit            Exit manager\n"
        )
