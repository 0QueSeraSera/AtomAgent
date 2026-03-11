"""Channel adapter interface for inbound/outbound IM integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from atom_agent.bus.events import InboundMessage, OutboundMessage

InboundCallback = Callable[[InboundMessage], Awaitable[None]]


class ChannelAdapter(ABC):
    """Abstract adapter contract implemented by each IM channel integration."""

    def __init__(self, channel: str):
        clean = channel.strip()
        if not clean or clean != channel:
            raise ValueError("Channel name must be a non-empty trimmed string")
        self._channel = clean

    @property
    def channel(self) -> str:
        """Stable channel identifier (for example: `feishu`)."""
        return self._channel

    @abstractmethod
    async def start(self, on_inbound: InboundCallback) -> None:
        """Start the adapter and register inbound callback."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the adapter and release resources."""

    @abstractmethod
    async def send(self, message: OutboundMessage) -> None:
        """Send one outbound message through this channel."""
