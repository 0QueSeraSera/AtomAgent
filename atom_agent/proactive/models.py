"""Data models for proactive configuration parsing and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

TaskKind = Literal["once", "cron", "interval"]
TaskRuntimeStatus = Literal["idle", "running"]


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


@dataclass
class ProactiveTaskRuntimeState:
    """Runtime state for one proactive task."""

    task_id: str
    status: TaskRuntimeStatus = "idle"
    next_run: datetime | None = None
    next_base_run: datetime | None = None
    last_run: datetime | None = None
    last_status: str | None = None
    last_error: str | None = None
    completed_at: datetime | None = None
    last_scheduled_run: datetime | None = None
    last_scheduled_base: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize runtime state to JSON-safe dictionary."""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "next_base_run": self.next_base_run.isoformat() if self.next_base_run else None,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_status": self.last_status,
            "last_error": self.last_error,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "last_scheduled_run": (
                self.last_scheduled_run.isoformat() if self.last_scheduled_run else None
            ),
            "last_scheduled_base": (
                self.last_scheduled_base.isoformat() if self.last_scheduled_base else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProactiveTaskRuntimeState":
        """Create runtime state from persisted dictionary."""
        return cls(
            task_id=data["task_id"],
            status=data.get("status", "idle"),
            next_run=_parse_dt(data.get("next_run")),
            next_base_run=_parse_dt(data.get("next_base_run")),
            last_run=_parse_dt(data.get("last_run")),
            last_status=data.get("last_status"),
            last_error=data.get("last_error"),
            completed_at=_parse_dt(data.get("completed_at")),
            last_scheduled_run=_parse_dt(data.get("last_scheduled_run")),
            last_scheduled_base=_parse_dt(data.get("last_scheduled_base")),
        )


@dataclass
class ProactiveRuntimeState:
    """Runtime state for all proactive tasks in one workspace."""

    tasks: dict[str, ProactiveTaskRuntimeState] = field(default_factory=dict)

    def get_or_create_task(self, task_id: str) -> ProactiveTaskRuntimeState:
        """Get task runtime state, creating a default entry if absent."""
        state = self.tasks.get(task_id)
        if state is None:
            state = ProactiveTaskRuntimeState(task_id=task_id)
            self.tasks[task_id] = state
        return state

    def to_dict(self) -> dict[str, Any]:
        """Serialize runtime state to JSON-safe dictionary."""
        return {
            "tasks": {task_id: task_state.to_dict() for task_id, task_state in self.tasks.items()}
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProactiveRuntimeState":
        """Create runtime state from persisted dictionary."""
        tasks_raw = data.get("tasks", {})
        tasks = {
            task_id: ProactiveTaskRuntimeState.from_dict(task_data)
            for task_id, task_data in tasks_raw.items()
            if isinstance(task_data, dict)
        }
        return cls(tasks=tasks)


@dataclass(frozen=True)
class DueTask:
    """A task occurrence that is due for dispatch."""

    task_id: str
    kind: TaskKind
    session_key: str
    prompt: str
    scheduled_time: datetime
    base_time: datetime


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
