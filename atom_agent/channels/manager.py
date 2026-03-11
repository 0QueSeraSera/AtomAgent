"""Lifecycle and dispatch manager for channel adapters."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable

from atom_agent.bus.events import InboundMessage
from atom_agent.bus.queue import MessageBus
from atom_agent.channels.base import ChannelAdapter
from atom_agent.logging import get_logger

logger = get_logger("channels.manager")


class ChannelManager:
    """Coordinates channel adapters and bus dispatch loops."""

    def __init__(self, bus: MessageBus):
        self.bus = bus
        self._adapters: dict[str, ChannelAdapter] = {}
        self._running = False
        self._dispatcher_task: asyncio.Task | None = None

    @property
    def channels(self) -> list[str]:
        """List registered channel names."""
        return sorted(self._adapters.keys())

    def adapters(self) -> Iterable[ChannelAdapter]:
        """Iterate registered adapters."""
        return self._adapters.values()

    def register_adapter(self, adapter: ChannelAdapter) -> None:
        """Register a channel adapter by its stable channel name."""
        if self._running:
            raise RuntimeError("Cannot register adapters while manager is running")
        if adapter.channel in self._adapters:
            raise ValueError(f"Adapter already registered for channel: {adapter.channel}")
        self._adapters[adapter.channel] = adapter

    def unregister_adapter(self, channel: str) -> None:
        """Unregister a channel adapter."""
        if self._running:
            raise RuntimeError("Cannot unregister adapters while manager is running")
        self._adapters.pop(channel, None)

    async def start(self) -> None:
        """Start all adapters and outbound dispatch loop."""
        if self._running:
            return

        started: list[ChannelAdapter] = []
        try:
            for adapter in self._adapters.values():
                await adapter.start(self._make_inbound_handler(adapter.channel))
                started.append(adapter)
                logger.info("Channel adapter started", extra={"channel": adapter.channel})
        except Exception:
            for adapter in reversed(started):
                try:
                    await adapter.stop()
                except Exception as stop_err:  # pragma: no cover - best-effort cleanup
                    logger.warning(
                        "Failed to stop adapter after start failure",
                        extra={"channel": adapter.channel, "error": str(stop_err)},
                    )
            raise

        self._running = True
        self._dispatcher_task = asyncio.create_task(self._dispatch_outbound())

    async def stop(self) -> None:
        """Stop outbound loop and all adapters."""
        self._running = False

        if self._dispatcher_task is not None:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass
            self._dispatcher_task = None

        for adapter in self._adapters.values():
            try:
                await adapter.stop()
                logger.info("Channel adapter stopped", extra={"channel": adapter.channel})
            except Exception as err:
                logger.error(
                    "Channel adapter stop failed",
                    extra={"channel": adapter.channel, "error": str(err)},
                )

    def _make_inbound_handler(self, channel: str):
        async def _handle(msg: InboundMessage) -> None:
            if msg.channel != channel:
                # Keep adapter channel authoritative for routing consistency.
                msg.channel = channel
            await self.bus.publish_inbound(msg)

        return _handle

    async def _dispatch_outbound(self) -> None:
        while self._running:
            try:
                msg = await self.bus.consume_outbound()
            except asyncio.CancelledError:
                break

            adapter = self._adapters.get(msg.channel)
            if adapter is None:
                logger.warning(
                    "Dropping outbound message for unknown channel",
                    extra={"channel": msg.channel, "chat_id": msg.chat_id},
                )
                continue

            try:
                await adapter.send(msg)
            except Exception as err:
                logger.error(
                    "Channel send failed",
                    extra={"channel": msg.channel, "chat_id": msg.chat_id, "error": str(err)},
                )
