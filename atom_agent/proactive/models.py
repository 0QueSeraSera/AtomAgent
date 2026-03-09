"""Data models for proactive configuration parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

TaskKind = Literal["once", "cron", "interval"]


@dataclass(frozen=True)
class ProactiveValidationIssue:
    """A structured validation issue for machine-friendly handling."""

    code: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Serialize issue as a plain dictionary."""
        return {"code": self.code, "path": self.path, "message": self.message}


class ProactiveValidationError(ValueError):
    """Raised when proactive configuration fails validation."""

    def __init__(self, issues: list[ProactiveValidationIssue]):
        super().__init__("Invalid proactive configuration")
        self.issues = issues

    def __str__(self) -> str:
        joined = "; ".join(f"{i.path}: {i.message}" for i in self.issues)
        return f"Invalid proactive configuration: {joined}"


@dataclass
class ProactiveTaskConfig:
    """Normalized proactive task definition."""

    task_id: str
    kind: TaskKind
    session_key: str
    prompt: str
    enabled: bool = True
    jitter_sec: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    at: datetime | None = None
    cron: str | None = None
    every_sec: int | None = None

    def schedule_summary(self) -> str:
        """Human-readable schedule summary."""
        if self.kind == "once":
            at_text = self.at.isoformat() if self.at else "<missing>"
            return f"once at {at_text}"
        if self.kind == "cron":
            return f"cron `{self.cron}`"
        return f"every {self.every_sec}s"

    def to_dict(self) -> dict[str, Any]:
        """Serialize task for JSON/debug output."""
        data: dict[str, Any] = {
            "id": self.task_id,
            "kind": self.kind,
            "session_key": self.session_key,
            "prompt": self.prompt,
            "enabled": self.enabled,
            "jitter_sec": self.jitter_sec,
            "metadata": self.metadata,
        }
        if self.at:
            data["at"] = self.at.isoformat()
        if self.cron is not None:
            data["cron"] = self.cron
        if self.every_sec is not None:
            data["every_sec"] = self.every_sec
        return data


@dataclass
class ProactiveConfig:
    """Normalized proactive workspace configuration."""

    version: int
    enabled: bool
    timezone: str
    tasks: list[ProactiveTaskConfig]
    source_path: Path | None = None

    @property
    def active_tasks(self) -> list[ProactiveTaskConfig]:
        """Enabled tasks that can be scheduled."""
        return [task for task in self.tasks if task.enabled]

    def to_dict(self) -> dict[str, Any]:
        """Serialize normalized config for debug/CLI views."""
        return {
            "version": self.version,
            "enabled": self.enabled,
            "timezone": self.timezone,
            "tasks": [task.to_dict() for task in self.tasks],
            "source_path": str(self.source_path) if self.source_path else None,
        }
