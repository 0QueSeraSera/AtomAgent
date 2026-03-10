"""Gateway host runtime for channel-driven IM operation."""

from __future__ import annotations

import asyncio
from pathlib import Path

from atom_agent.agent import AgentLoop
from atom_agent.bus.queue import MessageBus
from atom_agent.channels import ChannelAdapter, ChannelManager
from atom_agent.logging import get_logger
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
    ):
        self.workspace = workspace
        self.workspace_name = workspace_name or workspace.name
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

        self._agent_task = asyncio.create_task(self.agent.run())
        try:
            await self.channels.start()
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

    async def __aenter__(self) -> "GatewayRuntime":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()
