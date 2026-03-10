"""Integration-style tests for gateway runtime wiring."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from atom_agent.bus.events import InboundMessage, OutboundMessage
from atom_agent.channels import ChannelAdapter, InboundCallback
from atom_agent.gateway import GatewayRuntime
from atom_agent.provider.base import LLMProvider, LLMResponse
from atom_agent.workspace import WorkspaceManager


class DummyProvider(LLMProvider):
    """Minimal provider for gateway runtime tests."""

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="gateway reply")

    def get_default_model(self) -> str:
        return "dummy-model"


@dataclass
class FakeAdapter(ChannelAdapter):
    """In-memory adapter for gateway runtime tests."""

    _channel: str
    start_calls: int = 0
    stop_calls: int = 0
    inbound_cb: InboundCallback | None = None
    sent: list[OutboundMessage] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__init__(self._channel)

    async def start(self, on_inbound: InboundCallback) -> None:
        self.start_calls += 1
        self.inbound_cb = on_inbound

    async def stop(self) -> None:
        self.stop_calls += 1

    async def send(self, message: OutboundMessage) -> None:
        self.sent.append(message)

    async def emit(self, message: InboundMessage) -> None:
        if self.inbound_cb is None:
            raise RuntimeError("Adapter not started")
        await self.inbound_cb(message)


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("Condition not met before timeout")


@pytest.mark.asyncio
async def test_gateway_runtime_processes_inbound_and_sends_outbound(tmp_path: Path) -> None:
    workspace = tmp_path / "gw-runtime"
    WorkspaceManager(workspace).init_workspace(name="gw-runtime")

    runtime = GatewayRuntime(provider=DummyProvider(), workspace=workspace)
    adapter = FakeAdapter("feishu")
    runtime.register_adapter(adapter)

    await runtime.start()

    await adapter.emit(
        InboundMessage(channel="feishu", sender_id="u1", chat_id="chat-1", content="hello")
    )
    await _wait_for(lambda: len(adapter.sent) > 0)

    assert adapter.sent[0].channel == "feishu"
    assert adapter.sent[0].chat_id == "chat-1"
    assert "gateway reply" in adapter.sent[0].content

    await runtime.stop()


@pytest.mark.asyncio
async def test_gateway_runtime_start_stop_are_idempotent(tmp_path: Path) -> None:
    workspace = tmp_path / "gw-idempotent"
    WorkspaceManager(workspace).init_workspace(name="gw-idempotent")

    runtime = GatewayRuntime(provider=DummyProvider(), workspace=workspace)
    adapter = FakeAdapter("feishu")
    runtime.register_adapter(adapter)

    await runtime.start()
    await runtime.start()
    assert runtime.running is True
    assert adapter.start_calls == 1

    await runtime.stop()
    await runtime.stop()
    assert runtime.running is False
    assert adapter.stop_calls == 1
