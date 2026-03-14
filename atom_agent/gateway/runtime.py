"""Gateway host runtime for channel-driven IM operation."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path

from atom_agent.agent import AgentLoop
from atom_agent.bus.queue import MessageBus
from atom_agent.channels import ChannelAdapter, ChannelManager
from atom_agent.logging import get_logger
from atom_agent.proactive import (
    ProactiveValidationError,
    build_due_inbound_message,
    evaluate_due_tasks,
    load_runtime_state,
    mark_task_finished,
    mark_task_started,
    parse_proactive_file,
    resolve_due_target,
    save_runtime_state,
)
from atom_agent.provider.base import LLMProvider

logger = get_logger("gateway.runtime")


class GatewayRuntime:
    """Long-running host runtime for channels + agent loop."""

    def __init__(
        self,
        *,
        provider: LLMProvider,
        workspace: Path,
        workspace_name: str | None = None,
        model: str | None = None,
        proactive_poll_sec: float = 30.0,
    ):
        self.workspace = workspace
        self.workspace_name = workspace_name or workspace.name
        self.proactive_poll_sec = proactive_poll_sec
        self.bus = MessageBus()
        self.agent = AgentLoop(
            bus=self.bus,
            provider=provider,
            workspace=workspace,
            workspace_name=self.workspace_name,
            model=model,
        )
        self.channels = ChannelManager(self.bus)

        self._agent_task: asyncio.Task | None = None
        self._proactive_task: asyncio.Task | None = None
        self._proactive_stop = asyncio.Event()
        self._running = False

    @property
    def running(self) -> bool:
        """Return runtime running state."""
        return self._running

    def register_adapter(self, adapter: ChannelAdapter) -> None:
        """Register a channel adapter before start."""
        self.channels.register_adapter(adapter)

    def unregister_adapter(self, channel: str) -> None:
        """Unregister a channel adapter before start."""
        self.channels.unregister_adapter(channel)

    async def start(self) -> None:
        """Start agent loop and channel manager."""
        if self._running:
            return

        self._proactive_stop.clear()
        self._agent_task = asyncio.create_task(self.agent.run())
        try:
            await self.channels.start()
            self._proactive_task = asyncio.create_task(self._run_proactive_loop())
        except Exception:
            self.agent.stop()
            if self._agent_task is not None:
                self._agent_task.cancel()
                try:
                    await self._agent_task
                except asyncio.CancelledError:
                    pass
                finally:
                    self._agent_task = None
            if self._proactive_task is not None:
                self._proactive_task.cancel()
                try:
                    await self._proactive_task
                except asyncio.CancelledError:
                    pass
                finally:
                    self._proactive_task = None
            raise

        self._running = True
        logger.info(
            "Gateway runtime started",
            extra={
                "workspace": self.workspace_name,
                "channels": self.channels.channels,
            },
        )

    async def stop(self) -> None:
        """Stop channel manager and agent loop gracefully."""
        if not self._running and self._agent_task is None:
            return

        self._running = False
        self.agent.stop()
        self._proactive_stop.set()

        if self._proactive_task is not None:
            try:
                await asyncio.wait_for(self._proactive_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._proactive_task.cancel()
                try:
                    await self._proactive_task
                except asyncio.CancelledError:
                    pass
            finally:
                self._proactive_task = None

        await self.channels.stop()

        if self._agent_task is not None:
            try:
                await asyncio.wait_for(self._agent_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._agent_task.cancel()
                try:
                    await self._agent_task
                except asyncio.CancelledError:
                    pass
            finally:
                self._agent_task = None

        logger.info("Gateway runtime stopped", extra={"workspace": self.workspace_name})

    async def _run_proactive_loop(self) -> None:
        """Poll PROACTIVE.md, enqueue due tasks, and persist runtime state."""
        logger.info(
            "Gateway proactive loop starting",
            extra={"workspace": self.workspace_name, "poll_sec": self.proactive_poll_sec},
        )
        while not self._proactive_stop.is_set():
            try:
                await self._run_proactive_once()
            except Exception as err:
                logger.error(
                    "Gateway proactive loop cycle failed",
                    extra={"workspace": self.workspace_name, "error": str(err)},
                )

            try:
                await asyncio.wait_for(self._proactive_stop.wait(), timeout=self.proactive_poll_sec)
            except asyncio.TimeoutError:
                continue
        logger.info("Gateway proactive loop stopped", extra={"workspace": self.workspace_name})

    async def _run_proactive_once(self) -> None:
        proactive_path = self.workspace / "PROACTIVE.md"
        if not proactive_path.exists():
            return

        try:
            config = parse_proactive_file(proactive_path)
        except ProactiveValidationError as err:
            logger.warning(
                "Invalid PROACTIVE configuration",
                extra={
                    "workspace": self.workspace_name,
                    "issues": [issue.to_dict() for issue in err.issues],
                },
            )
            return
        except Exception as err:
            logger.warning(
                "Failed to parse PROACTIVE configuration",
                extra={"workspace": self.workspace_name, "error": str(err)},
            )
            return

        if not config.enabled:
            return

        state = load_runtime_state(self.workspace)
        due_tasks = evaluate_due_tasks(config, state)
        if not due_tasks:
            save_runtime_state(self.workspace, state)
            return

        task_by_id = {task.task_id: task for task in config.tasks}
        for due in due_tasks:
            task = task_by_id.get(due.task_id)
            if task is None:
                continue

            mark_task_started(state, due, started_at=datetime.now())
            save_runtime_state(self.workspace, state)
            try:
                session_override = self._resolve_proactive_session_override(due)
                if session_override is None:
                    mark_task_finished(
                        task,
                        state,
                        timezone_name=config.timezone,
                        finished_at=datetime.now(),
                        success=True,
                    )
                    logger.info(
                        "Proactive task suppressed",
                        extra={
                            "workspace": self.workspace_name,
                            "task_id": due.task_id,
                            "reason": "feishu_chitchat_disabled",
                        },
                    )
                    continue

                message = build_due_inbound_message(due)
                if session_override:
                    message.session_key_override = session_override
                await self.bus.publish_inbound(message)
                mark_task_finished(
                    task,
                    state,
                    timezone_name=config.timezone,
                    finished_at=datetime.now(),
                    success=True,
                )
                logger.info(
                    "Proactive task enqueued",
                    extra={
                        "workspace": self.workspace_name,
                        "task_id": due.task_id,
                        "session_key": due.session_key,
                        "delivery": message.chat_id,
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
                logger.error(
                    "Proactive task enqueue failed",
                    extra={"workspace": self.workspace_name, "task_id": due.task_id, "error": str(err)},
                )
            finally:
                save_runtime_state(self.workspace, state)

    def _resolve_proactive_session_override(self, due) -> str | None:
        """
        Resolve channel-specific proactive memory session override.

        Returns:
            - explicit session key override string when channel wants custom memory scope
            - None when proactive delivery should be suppressed
            - empty string when no override is needed
        """
        channel, chat_id, _ = resolve_due_target(due)
        if channel != "feishu" or not due.chitchat_mode:
            return ""

        for adapter in self.channels.adapters():
            if adapter.channel != "feishu":
                continue
            resolver = getattr(adapter, "resolve_proactive_session_key", None)
            if not callable(resolver):
                return ""
            return resolver(chat_id=chat_id, chitchat_mode=True) or None
        return ""

    async def __aenter__(self) -> "GatewayRuntime":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()
