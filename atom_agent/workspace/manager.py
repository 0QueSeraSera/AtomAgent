"""Workspace management for AtomAgent."""

from __future__ import annotations

import platform
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from atom_agent.logging import get_logger

logger = get_logger("workspace.manager")

# Bootstrap files that define the agent's context
BOOTSTRAP_FILES = ["IDENTITY.md", "SOUL.md", "AGENTS.md", "USER.md", "TOOLS.md"]

# Required directories in a workspace
WORKSPACE_DIRS = ["memory", "sessions"]

DEFAULT_MEMORY_CONTENT = "# Long-term Memory\n\n- No persistent facts recorded yet.\n"
DEFAULT_HISTORY_CONTENT = "# Conversation History\n\n- No archived sessions yet.\n"


def _default_workspace_path() -> Path:
    """Resolve default workspace from global registry."""
    try:
        from atom_agent.config import ConfigManager

        return ConfigManager().get_active_workspace_path()
    except Exception:
        return Path.home() / ".atom-agents" / "workspaces" / "default"


@dataclass
class WorkspaceConfig:
    """Configuration for a workspace."""

    path: Path
    name: str = "default"
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": str(self.path),
            "name": self.name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkspaceConfig":
        """Create from dictionary."""
        return cls(
            path=Path(data["path"]),
            name=data.get("name", "default"),
            created_at=(
                datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
            ),
            metadata=data.get("metadata", {}),
        )


class WorkspaceManager:
    """
    Manages workspace initialization, validation, and configuration.

    A workspace is a directory containing:
    - Bootstrap files (IDENTITY.md, SOUL.md, etc.)
    - memory/ directory for MEMORY.md and HISTORY.md
    - sessions/ directory for session JSONL files
    """

    def __init__(self, workspace_path: Path | None = None):
        """Initialize workspace manager."""
        self.workspace_path = workspace_path or _default_workspace_path()
        self._templates_dir = Path(__file__).parent / "templates"

    @property
    def memory_dir(self) -> Path:
        """Get the memory directory path."""
        return self.workspace_path / "memory"

    @property
    def sessions_dir(self) -> Path:
        """Get the sessions directory path."""
        return self.workspace_path / "sessions"

    def init_workspace(
        self, path: Path | None = None, *, force: bool = False, name: str = "default"
    ) -> WorkspaceConfig:
        """
        Initialize a new workspace with default files.

        Args:
            path: Workspace path (uses self.workspace_path if None)
            force: Overwrite existing files if True
            name: Name for the workspace

        Returns:
            WorkspaceConfig for the initialized workspace
        """
        target_path = path or self.workspace_path
        target_path = target_path.expanduser().resolve()
        self.workspace_path = target_path

        logger.info("Initializing workspace", extra={"path": str(target_path)})

        # Create main directory
        target_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        for dirname in WORKSPACE_DIRS:
            dir_path = target_path / dirname
            dir_path.mkdir(exist_ok=True)

        # Copy template files
        for filename in BOOTSTRAP_FILES:
            self._init_file(target_path / filename, force=force)

        # Create memory files with starter content
        memory_file = target_path / "memory" / "MEMORY.md"
        history_file = target_path / "memory" / "HISTORY.md"
        if force or not memory_file.exists():
            memory_file.write_text(DEFAULT_MEMORY_CONTENT, encoding="utf-8")
        if force or not history_file.exists():
            history_file.write_text(DEFAULT_HISTORY_CONTENT, encoding="utf-8")

        config = WorkspaceConfig(
            path=target_path,
            name=name,
            created_at=datetime.now(),
        )

        logger.info("Workspace initialized", extra={"path": str(target_path)})
        return config

    def _init_file(self, target: Path, *, force: bool = False) -> bool:
        """
        Initialize a single file from template.

        Returns:
            True if file was created, False if skipped
        """
        if target.exists() and not force:
            logger.debug("File exists, skipping", extra={"file": str(target)})
            return False

        template_path = self._templates_dir / target.name
        if template_path.exists():
            shutil.copy2(template_path, target)
            logger.debug("Created file from template", extra={"file": str(target)})
        else:
            target.touch()
            logger.debug("Created empty file", extra={"file": str(target)})

        return True

    def validate_workspace(self, path: Path | None = None) -> list[str]:
        """
        Validate a workspace structure.

        Args:
            path: Workspace path (uses self.workspace_path if None)

        Returns:
            List of validation errors (empty if valid)
        """
        target_path = (path or self.workspace_path).expanduser().resolve()
        errors = []

        # Check main directory
        if not target_path.is_dir():
            errors.append(f"Workspace directory does not exist: {target_path}")
            return errors

        # Check subdirectories
        for dirname in WORKSPACE_DIRS:
            dir_path = target_path / dirname
            if not dir_path.is_dir():
                errors.append(f"Missing directory: {dirname}")

        # Check for at least IDENTITY.md
        identity_file = target_path / "IDENTITY.md"
        if not identity_file.exists():
            errors.append("Missing IDENTITY.md file")

        return errors

    def get_workspace_config(self, path: Path | None = None) -> WorkspaceConfig:
        """
        Get configuration for a workspace.

        Args:
            path: Workspace path (uses self.workspace_path if None)

        Returns:
            WorkspaceConfig for the workspace
        """
        target_path = (path or self.workspace_path).expanduser().resolve()
        return WorkspaceConfig(
            path=target_path,
            name=target_path.name,
        )

    def get_identity(self, path: Path | None = None) -> str:
        """
        Get the identity content for a workspace.

        Args:
            path: Workspace path (uses self.workspace_path if None)

        Returns:
            Identity content (from IDENTITY.md or default template)
        """
        target_path = (path or self.workspace_path).expanduser().resolve()
        identity_file = target_path / "IDENTITY.md"

        if identity_file.exists():
            return identity_file.read_text(encoding="utf-8")

        # Return default template
        template_path = self._templates_dir / "IDENTITY.md"
        if template_path.exists():
            return template_path.read_text(encoding="utf-8")

        # Ultimate fallback
        return """# AtomAgent

You are AtomAgent, a proactive AI assistant capable of long-running tasks and autonomous operation.

## Core Traits
- Helpful and responsive
- Thorough in task completion
- Proactive in communication
- Adaptable to user preferences

## Behavioral Guidelines
- State intent before taking action
- Verify assumptions before proceeding
- Communicate progress on long tasks
- Ask for clarification when uncertain
"""

    def get_bootstrap_content(self, path: Path | None = None) -> dict[str, str]:
        """
        Get all bootstrap file contents for a workspace.

        Args:
            path: Workspace path (uses self.workspace_path if None)

        Returns:
            Dict mapping filename to content for existing files
        """
        target_path = (path or self.workspace_path).expanduser().resolve()
        contents = {}

        for filename in BOOTSTRAP_FILES:
            file_path = target_path / filename
            if file_path.exists():
                contents[filename] = file_path.read_text(encoding="utf-8")

        return contents

    def build_runtime_context(self, channel: str | None = None, chat_id: str | None = None) -> str:
        """
        Build untrusted runtime metadata block.

        Args:
            channel: Optional channel identifier
            chat_id: Optional chat identifier

        Returns:
            Runtime context string
        """
        import time

        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        runtime = f"{'macOS' if platform.system() == 'Darwin' else platform.system()} {platform.machine()}, Python {platform.python_version()}"

        lines = [
            f"Current Time: {now} ({tz})",
            f"Platform: {runtime}",
            f"Workspace: {self.workspace_path}",
        ]
        if channel and chat_id:
            lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]

        return "\n".join(lines)

    def list_sessions(self, path: Path | None = None) -> list[dict[str, Any]]:
        """
        List all sessions in the workspace.

        Args:
            path: Workspace path (uses self.workspace_path if None)

        Returns:
            List of session info dicts
        """
        target_path = (path or self.workspace_path).expanduser().resolve()
        sessions_dir = target_path / "sessions"
        sessions = []

        if not sessions_dir.exists():
            return sessions

        import json

        for session_file in sessions_dir.glob("*.jsonl"):
            try:
                with open(session_file, encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            key = data.get("key") or session_file.stem.replace("_", ":", 1)
                            sessions.append(
                                {
                                    "key": key,
                                    "created_at": data.get("created_at"),
                                    "updated_at": data.get("updated_at"),
                                    "path": str(session_file),
                                }
                            )
            except Exception:
                continue

        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
