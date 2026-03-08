"""Workspace management for AtomAgent.

This module provides workspace initialization, validation, and configuration
for file-based agent identity and context management.

Example:
    from atom_agent.workspace import WorkspaceManager

    # Initialize a new workspace
    manager = WorkspaceManager(Path("./my-workspace"))
    manager.init_workspace()

    # Get identity content
    identity = manager.get_identity()

    # Validate workspace
    errors = manager.validate_workspace()
"""

from __future__ import annotations

from pathlib import Path

from atom_agent.workspace.manager import (
    BOOTSTRAP_FILES,
    WORKSPACE_DIRS,
    WorkspaceConfig,
    WorkspaceManager,
)

__all__ = [
    "BOOTSTRAP_FILES",
    "WORKSPACE_DIRS",
    "WorkspaceConfig",
    "WorkspaceManager",
]
