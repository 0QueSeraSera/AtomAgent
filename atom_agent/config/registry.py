"""Configuration system for AtomAgent with workspace registry support.

This module provides:
- Global configuration management
- Workspace registry for multiple workspaces
- Configuration file support (config.yaml)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default AtomAgent directory
DEFAULT_ATOMAGENT_DIR = Path.home() / ".atomagent"
DEFAULT_WORKSPACES_DIR = DEFAULT_ATOMAGENT_DIR / "workspaces"
DEFAULT_CONFIG_FILE = DEFAULT_ATOMAGENT_DIR / "config.json"


@dataclass
class WorkspaceEntry:
    """Entry for a registered workspace."""

    name: str
    path: Path
    created_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "path": str(self.path),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkspaceEntry":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            path=Path(data["path"]),
            created_at=(
                datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
            ),
            metadata=data.get("metadata", {}),
        )


@dataclass
class GlobalConfig:
    """Global AtomAgent configuration."""

    active_workspace: str = "default"
    default_provider: str = "deepseek"
    workspaces: dict[str, WorkspaceEntry] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "active_workspace": self.active_workspace,
            "default_provider": self.default_provider,
            "workspaces": {k: v.to_dict() for k, v in self.workspaces.items()},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GlobalConfig":
        """Create from dictionary."""
        workspaces = {}
        for name, entry_data in data.get("workspaces", {}).items():
            workspaces[name] = WorkspaceEntry.from_dict(entry_data)

        return cls(
            active_workspace=data.get("active_workspace", "default"),
            default_provider=data.get("default_provider", "deepseek"),
            workspaces=workspaces,
            created_at=(
                datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
            ),
            updated_at=(
                datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else None
            ),
        )


class ConfigManager:
    """
    Manages global AtomAgent configuration.

    Configuration is stored in ~/.atomagent/config.json by default.
    """

    def __init__(self, config_file: Path | None = None):
        self.config_file = config_file or DEFAULT_CONFIG_FILE
        self._config: GlobalConfig | None = None

    @property
    def config(self) -> GlobalConfig:
        """Get the current configuration, loading if necessary."""
        if self._config is None:
            self._config = self.load()
        return self._config

    def load(self) -> GlobalConfig:
        """Load configuration from file."""
        if not self.config_file.exists():
            logger.info("Config file not found, creating default")
            return self._create_default_config()

        try:
            with open(self.config_file, encoding="utf-8") as f:
                data = json.load(f)
            return GlobalConfig.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load config: {e}, using defaults")
            return self._create_default_config()

    def save(self) -> None:
        """Save configuration to file."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config.updated_at = datetime.now()

        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)

        logger.info(f"Config saved to {self.config_file}")

    def _create_default_config(self) -> GlobalConfig:
        """Create default configuration with default workspace."""
        config = GlobalConfig(
            active_workspace="default",
            default_provider="deepseek",
            workspaces={
                "default": WorkspaceEntry(
                    name="default",
                    path=DEFAULT_WORKSPACES_DIR / "default",
                    created_at=datetime.now(),
                )
            },
            created_at=datetime.now(),
        )
        self._config = config
        return config

    def get_active_workspace_path(self) -> Path:
        """Get the path to the active workspace."""
        # Check environment variable override
        env_workspace = os.environ.get("ATOMAGENT_WORKSPACE")
        if env_workspace:
            return Path(env_workspace)

        active_name = self.config.active_workspace
        if active_name in self.config.workspaces:
            return self.config.workspaces[active_name].path

        # Fallback to default
        return DEFAULT_WORKSPACES_DIR / "default"

    def set_active_workspace(self, name: str) -> bool:
        """Set the active workspace by name."""
        if name not in self.config.workspaces:
            logger.warning(f"Workspace '{name}' not found")
            return False

        self.config.active_workspace = name
        self.save()
        return True

    def register_workspace(
        self, name: str, path: Path, metadata: dict[str, Any] | None = None
    ) -> WorkspaceEntry:
        """Register a new workspace."""
        entry = WorkspaceEntry(
            name=name,
            path=path,
            created_at=datetime.now(),
            metadata=metadata or {},
        )
        self.config.workspaces[name] = entry
        self.save()
        return entry

    def unregister_workspace(self, name: str) -> bool:
        """Unregister a workspace."""
        if name not in self.config.workspaces:
            return False

        del self.config.workspaces[name]

        # If removing active workspace, switch to default
        if self.config.active_workspace == name:
            self.config.active_workspace = "default"

        self.save()
        return True

    def list_workspaces(self) -> list[WorkspaceEntry]:
        """List all registered workspaces."""
        return list(self.config.workspaces.values())


class WorkspaceRegistry:
    """
    Registry for managing multiple workspaces.

    Provides high-level operations for workspace management:
    - List, create, delete workspaces
    - Switch active workspace
    - Import/export sessions
    """

    def __init__(self, config_manager: ConfigManager | None = None):
        self.config_manager = config_manager or ConfigManager()
        self._ensure_default_workspace()

    def _ensure_default_workspace(self) -> None:
        """Ensure default workspace exists."""
        default_path = self.config_manager.get_active_workspace_path()
        if not default_path.exists():
            from atom_agent.workspace import WorkspaceManager

            WorkspaceManager(default_path).init_workspace(name="default")

    def list_workspaces(self) -> list[WorkspaceEntry]:
        """List all known workspaces."""
        return self.config_manager.list_workspaces()

    def get_workspace(self, name: str) -> WorkspaceEntry | None:
        """Get workspace by name."""
        return self.config_manager.config.workspaces.get(name)

    def create_workspace(
        self, name: str, path: Path | None = None, template: str | None = None
    ) -> WorkspaceEntry:
        """
        Create a new workspace.

        Args:
            name: Name for the workspace
            path: Optional path (defaults to ~/.atomagent/workspaces/{name})
            template: Optional template name for initialization

        Returns:
            The created WorkspaceEntry
        """
        from atom_agent.workspace import WorkspaceManager

        if path is None:
            path = DEFAULT_WORKSPACES_DIR / name

        # Initialize workspace
        manager = WorkspaceManager(path)
        manager.init_workspace(path, name=name)

        # Register in config
        metadata = {"template": template} if template else None
        return self.config_manager.register_workspace(name, path, metadata)

    def delete_workspace(self, name: str, *, delete_files: bool = False) -> bool:
        """
        Remove a workspace from the registry.

        Args:
            name: Name of the workspace to remove
            delete_files: If True, also delete the workspace files

        Returns:
            True if workspace was removed
        """
        entry = self.get_workspace(name)
        if not entry:
            return False

        # Don't allow deleting the default workspace
        if name == "default":
            logger.warning("Cannot delete default workspace")
            return False

        # Remove from registry
        self.config_manager.unregister_workspace(name)

        # Optionally delete files
        if delete_files:
            import shutil

            try:
                shutil.rmtree(entry.path)
            except Exception as e:
                logger.warning(f"Failed to delete workspace files: {e}")

        return True

    def get_active_workspace(self) -> WorkspaceEntry:
        """Get the current active workspace."""
        active_name = self.config_manager.config.active_workspace
        entry = self.get_workspace(active_name)
        if not entry:
            # Fallback to default
            entry = self.get_workspace("default")
        if not entry:
            # Create default if needed
            entry = self.create_workspace("default")
        return entry

    def set_active_workspace(self, name: str) -> bool:
        """Switch active workspace."""
        return self.config_manager.set_active_workspace(name)

    def get_workspace_path(self, name: str | None = None) -> Path:
        """Get path to a workspace (active if name is None)."""
        if name:
            entry = self.get_workspace(name)
            if entry:
                return entry.path
            raise ValueError(f"Workspace '{name}' not found")

        return self.config_manager.get_active_workspace_path()
