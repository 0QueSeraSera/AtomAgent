"""Daemon orchestration service for proactive task execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from atom_agent.config import ConfigManager, WorkspaceEntry
from atom_agent.logging import get_logger
from atom_agent.proactive import (
    evaluate_due_tasks,
    load_runtime_state,
    mark_task_finished,
    mark_task_started,
    parse_proactive_file,
    save_runtime_state,
)
from atom_agent.proactive.models import ProactiveValidationError
from atom_agent.provider.base import LLMProvider

from .runtime import WorkspaceRuntime

logger = get_logger("daemon.service")


@dataclass
class DaemonDispatchReport:
    """One task dispatch attempt report."""

    workspace: str
    task_id: str
    status: str
    output_count: int = 0
    error: str | None = None


class DaemonService:
    """Run proactive scheduling and dispatch across one or more workspaces."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        model: str | None = None,
        poll_sec: float = 30.0,
        workspace_paths: list[Path] | None = None,
    ):
        self.provider = provider
        self.model = model
        self.poll_sec = poll_sec
        self.workspace_paths = [p.expanduser().resolve() for p in workspace_paths or []]
        self._stop_event = asyncio.Event()
        self._runtimes: dict[Path, WorkspaceRuntime] = {}

    def stop(self) -> None:
        """Request shutdown for run_forever loop."""
        self._stop_event.set()

    async def run_once(self) -> list[DaemonDispatchReport]:
        """Run one full daemon cycle across target workspaces."""
        reports: list[DaemonDispatchReport] = []
        for entry in self._workspace_entries():
            workspace_path = entry.path.expanduser().resolve()
            proactive_path = workspace_path / "PROACTIVE.md"
            if not proactive_path.exists():
                continue

            try:
                config = parse_proactive_file(proactive_path)
            except ProactiveValidationError as err:
                logger.warning(
                    "Invalid PROACTIVE configuration",
                    extra={
                        "workspace": str(workspace_path),
                        "issues": [issue.to_dict() for issue in err.issues],
                    },
                )
                continue
            except Exception as err:
                logger.warning(
                    "Failed to parse PROACTIVE configuration",
                    extra={"workspace": str(workspace_path), "error": str(err)},
                )
                continue

            if not config.enabled:
                continue

            state = load_runtime_state(workspace_path)
            due_tasks = evaluate_due_tasks(config, state)
            if not due_tasks:
                save_runtime_state(workspace_path, state)
                continue

            runtime = self._get_runtime(entry)
            task_by_id = {task.task_id: task for task in config.tasks}

            for due in due_tasks:
                task = task_by_id.get(due.task_id)
                if task is None:
                    continue
                mark_task_started(state, due, started_at=datetime.now())
                save_runtime_state(workspace_path, state)
                try:
                    outbound = await runtime.execute_due_task(due)
                    mark_task_finished(
                        task,
                        state,
                        timezone_name=config.timezone,
                        finished_at=datetime.now(),
                        success=True,
                    )
                    reports.append(
                        DaemonDispatchReport(
                            workspace=entry.name,
                            task_id=due.task_id,
                            status="success",
                            output_count=len(outbound),
                        )
                    )
                    logger.info(
                        "Proactive task dispatched",
                        extra={
                            "workspace": entry.name,
                            "task_id": due.task_id,
                            "outputs": len(outbound),
                        },
                    )
                except Exception as err:
                    mark_task_finished(
                        task,
                        state,
                        timezone_name=config.timezone,
                        finished_at=datetime.now(),
                        success=False,
                        error=str(err),
                    )
                    reports.append(
                        DaemonDispatchReport(
                            workspace=entry.name,
                            task_id=due.task_id,
                            status="failed",
                            error=str(err),
                        )
                    )
                    logger.error(
                        "Proactive task dispatch failed",
                        extra={"workspace": entry.name, "task_id": due.task_id, "error": str(err)},
                    )
                finally:
                    save_runtime_state(workspace_path, state)

        return reports

    async def run_forever(self) -> None:
        """Run daemon loop until stop() is called."""
        logger.info("Daemon loop starting", extra={"poll_sec": self.poll_sec})
        while not self._stop_event.is_set():
            await self.run_once()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_sec)
            except asyncio.TimeoutError:
                continue
        logger.info("Daemon loop stopped")

    def _workspace_entries(self) -> list[WorkspaceEntry]:
        if self.workspace_paths:
            return [
                WorkspaceEntry(name=path.name, path=path, created_at=None, metadata={})
                for path in self.workspace_paths
            ]
        return ConfigManager().list_workspaces()

    def _get_runtime(self, entry: WorkspaceEntry) -> WorkspaceRuntime:
        path = entry.path.expanduser().resolve()
        runtime = self._runtimes.get(path)
        if runtime is None:
            runtime = WorkspaceRuntime(
                workspace=path,
                workspace_name=entry.name,
                provider=self.provider,
                model=self.model,
            )
            self._runtimes[path] = runtime
        return runtime
