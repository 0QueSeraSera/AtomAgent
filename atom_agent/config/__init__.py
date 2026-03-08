"""Configuration management for AtomAgent.

This module provides:
- Global configuration management
- Workspace registry for multiple workspaces
- Environment variable overrides

Example:
    from atom_agent.config import ConfigManager, WorkspaceRegistry

    # Get active workspace path
    config = ConfigManager()
    workspace_path = config.get_active_workspace_path()

    # Manage workspaces
    registry = WorkspaceRegistry()
    registry.create_workspace("my-workspace")
    registry.set_active_workspace("my-workspace")
"""

from __future__ import annotations

from atom_agent.config.registry import (
    DEFAULT_ATOMAGENT_DIR,
    DEFAULT_CONFIG_FILE,
    DEFAULT_WORKSPACES_DIR,
    ConfigManager,
    GlobalConfig,
    WorkspaceEntry,
    WorkspaceRegistry,
)

__all__ = [
    "DEFAULT_ATOMAGENT_DIR",
    "DEFAULT_CONFIG_FILE",
    "DEFAULT_WORKSPACES_DIR",
    "ConfigManager",
    "GlobalConfig",
    "WorkspaceEntry",
    "WorkspaceRegistry",
]
