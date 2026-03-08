"""Logging configuration for AtomAgent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class LoggingConfig:
    """
    Configuration for AtomAgent logging.

    Supports environment variable overrides for all settings.
    """

    level: str = "INFO"
    format: Literal["text", "json"] = "text"
    output: Literal["stderr", "stdout", "file"] = "stderr"
    file_path: Path | None = None
    max_content_length: int = 200
    component_levels: dict[str, str] = field(default_factory=dict)
    # Verbose content logging - includes full prompts, responses, and tool results
    log_content: bool = False
    # Multi-channel file separation
    separate_channels: bool = False
    channels_to_log: list[str] | None = None  # None = log all channels
    log_dir: Path | None = None  # Base directory for log files (default: ./logs)

    def __post_init__(self) -> None:
        """Apply environment variable overrides."""
        # Override from environment variables if set
        if level := os.environ.get("ATOM_AGENT_LOG_LEVEL"):
            self.level = level.upper()

        if fmt := os.environ.get("ATOM_AGENT_LOG_FORMAT"):
            if fmt.lower() in ("text", "json"):
                self.format = fmt.lower()  # type: ignore

        if output := os.environ.get("ATOM_AGENT_LOG_OUTPUT"):
            if output.lower() in ("stderr", "stdout", "file"):
                self.output = output.lower()  # type: ignore

        if file_path := os.environ.get("ATOM_AGENT_LOG_FILE"):
            self.file_path = Path(file_path)

        # Verbose content logging
        if log_content := os.environ.get("ATOM_AGENT_LOG_CONTENT"):
            self.log_content = log_content.lower() in ("1", "true", "yes")

        # Multi-channel file separation
        if separate_channels := os.environ.get("ATOM_AGENT_LOG_SEPARATE_CHANNELS"):
            self.separate_channels = separate_channels.lower() in ("1", "true", "yes")

        if channels := os.environ.get("ATOM_AGENT_LOG_CHANNELS"):
            self.channels_to_log = [c.strip() for c in channels.split(",") if c.strip()]

        if log_dir := os.environ.get("ATOM_AGENT_LOG_DIR"):
            self.log_dir = Path(log_dir)

        # Validate level
        valid_levels = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "TRACE")
        if self.level.upper() not in valid_levels:
            self.level = "INFO"
        else:
            self.level = self.level.upper()
