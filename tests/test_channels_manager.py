"""Unit tests for channel manager lifecycle and dispatch behavior."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from atom_agent.bus.events import InboundMessage, OutboundMessage
from atom_agent.bus.queue import MessageBus
from atom_agent.channels import ChannelAdapter, ChannelManager, InboundCallback


@dataclass
class FakeAdapter(ChannelAdapter):
    """In-memory adapter used for channel manager tests."""

    _channel: str
    started: bool = False
    stopped: bool = False
    inbound_cb: InboundCallback | None = None
    sent: list[OutboundMessage] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__init__(self._channel)

    async def start(self, on_inbound: InboundCallback) -> None:
        self.started = True
        self.stopped = False
        self.inbound_cb = on_inbound

    async def stop(self) -> None:
        self.stopped = True

    async def send(self, message: OutboundMessage) -> None:
        self.sent.append(message)

    async def emit(self, message: InboundMessage) -> None:
        if self.inbound_cb is None:
            raise RuntimeError("Adapter not started")
        await self.inbound_cb(message)


async def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("Condition not met before timeout")


@pytest.mark.asyncio
async def test_channel_manager_routes_inbound_and_outbound() -> None:
    bus = MessageBus()
    manager = ChannelManager(bus)
    adapter = FakeAdapter("feishu")
    manager.register_adapter(adapter)

    await manager.start()

    await adapter.emit(
        InboundMessage(channel="wrong", sender_id="u1", chat_id="chat-1", content="hello")
    )
    inbound = await asyncio.wait_for(bus.consume_inbound(), timeout=1.0)
    assert inbound.channel == "feishu"
    assert inbound.chat_id == "chat-1"

    await bus.publish_outbound(
        OutboundMessage(channel="feishu", chat_id="chat-1", content="hi from agent")
    )
    await _wait_for(lambda: len(adapter.sent) == 1)
    assert adapter.sent[0].content == "hi from agent"

    await manager.stop()
    assert adapter.stopped is True


@pytest.mark.asyncio
async def test_channel_manager_drops_unknown_channel() -> None:
    bus = MessageBus()
    manager = ChannelManager(bus)
    await manager.start()

    await bus.publish_outbound(OutboundMessage(channel="unknown", chat_id="1", content="drop me"))
    await asyncio.sleep(0.05)

    await manager.stop()


def test_channel_manager_rejects_duplicate_registration() -> None:
    manager = ChannelManager(MessageBus())
    manager.register_adapter(FakeAdapter("feishu"))

    with pytest.raises(ValueError, match="already registered"):
        manager.register_adapter(FakeAdapter("feishu"))
