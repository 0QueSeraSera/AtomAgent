"""Integration-style tests for gateway runtime wiring."""

from __future__ import annotations

import asyncio
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from atom_agent.bus.events import InboundMessage, OutboundMessage
from atom_agent.channels import ChannelAdapter, InboundCallback
from atom_agent.gateway import GatewayRuntime
from atom_agent.proactive.state import load_runtime_state
from atom_agent.provider.base import LLMProvider, LLMResponse
from atom_agent.session import SessionManager
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


@dataclass
class FakeFeishuSessionAdapter(FakeAdapter):
    """Feishu-like adapter exposing proactive session resolver."""

    proactive_chitchat_enabled: bool = True

    def resolve_proactive_session_key(self, *, chat_id: str, chitchat_mode: bool) -> str | None:
        if not chitchat_mode:
            return f"feishu:{chat_id}"
        if not self.proactive_chitchat_enabled:
            return None
        return f"feishu:{chat_id}__chitchat"


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("Condition not met before timeout")


def _write_proactive(path: Path, payload: str) -> None:
    path.write_text(
        textwrap.dedent(
            f"""
            # Proactive Configuration

            ```json
            {payload}
            ```
            """
        ).strip(),
        encoding="utf-8",
    )


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


@pytest.mark.asyncio
async def test_gateway_runtime_dispatches_due_proactive_task(tmp_path: Path) -> None:
    workspace = tmp_path / "gw-proactive"
    WorkspaceManager(workspace).init_workspace(name="gw-proactive")

    _write_proactive(
        workspace / "PROACTIVE.md",
        """{
  "version": 1,
  "enabled": true,
  "timezone": "UTC",
  "tasks": [
    {
      "id": "wake-up",
      "kind": "once",
      "at": "2026-03-01T08:00:00+00:00",
      "session_key": "cli:memory-session",
      "target": {
        "channel": "feishu",
        "chat_id": "chat-target",
        "thread_id": "thread-123"
      },
      "prompt": "Send wake-up reminder."
    }
  ]
}""",
    )

    runtime = GatewayRuntime(provider=DummyProvider(), workspace=workspace, proactive_poll_sec=0.05)
    adapter = FakeAdapter("feishu")
    runtime.register_adapter(adapter)

    await runtime.start()
    await _wait_for(lambda: len(adapter.sent) > 0)
    await runtime.stop()

    assert adapter.sent[0].channel == "feishu"
    assert adapter.sent[0].chat_id == "chat-target"
    assert adapter.sent[0].metadata["task_id"] == "wake-up"
    assert adapter.sent[0].metadata["proactive"] is True
    assert adapter.sent[0].metadata["thread_id"] == "thread-123"

    state = load_runtime_state(workspace)
    assert state.tasks["wake-up"].completed_at is not None

    session = SessionManager(workspace, workspace.name).get_or_create("cli:memory-session")
    assert len(session.messages) > 0


@pytest.mark.asyncio
async def test_gateway_runtime_ignores_invalid_proactive_config(tmp_path: Path) -> None:
    workspace = tmp_path / "gw-invalid-proactive"
    WorkspaceManager(workspace).init_workspace(name="gw-invalid-proactive")
    (workspace / "PROACTIVE.md").write_text("# bad config", encoding="utf-8")

    runtime = GatewayRuntime(provider=DummyProvider(), workspace=workspace, proactive_poll_sec=0.05)
    adapter = FakeAdapter("feishu")
    runtime.register_adapter(adapter)

    await runtime.start()
    await asyncio.sleep(0.2)
    await runtime.stop()

    assert adapter.sent == []


@pytest.mark.asyncio
async def test_gateway_runtime_routes_feishu_chitchat_task_to_dedicated_session(tmp_path: Path) -> None:
    workspace = tmp_path / "gw-proactive-chitchat"
    WorkspaceManager(workspace).init_workspace(name="gw-proactive-chitchat")

    _write_proactive(
        workspace / "PROACTIVE.md",
        """{
  "version": 1,
  "enabled": true,
  "timezone": "UTC",
  "tasks": [
    {
      "id": "chitchat-ping",
      "kind": "once",
      "at": "2026-03-01T08:00:00+00:00",
      "session_key": "cli:legacy-memory",
      "target": {
        "channel": "feishu",
        "chat_id": "chat-target"
      },
      "chitchat_mode": true,
      "prompt": "Send a casual proactive ping."
    }
  ]
}""",
    )

    runtime = GatewayRuntime(provider=DummyProvider(), workspace=workspace, proactive_poll_sec=0.05)
    adapter = FakeFeishuSessionAdapter("feishu", proactive_chitchat_enabled=True)
    runtime.register_adapter(adapter)

    await runtime.start()
    await _wait_for(lambda: len(adapter.sent) > 0)
    await runtime.stop()

    assert adapter.sent[0].chat_id == "chat-target"
    assert adapter.sent[0].metadata["chitchat_mode"] is True

    chitchat_session = SessionManager(workspace, workspace.name).get_or_create(
        "feishu:chat-target__chitchat"
    )
    assert len(chitchat_session.messages) > 0

    legacy_session = SessionManager(workspace, workspace.name).get_or_create("cli:legacy-memory")
    assert len(legacy_session.messages) == 0


@pytest.mark.asyncio
async def test_gateway_runtime_suppresses_feishu_chitchat_task_when_disabled(tmp_path: Path) -> None:
    workspace = tmp_path / "gw-proactive-chitchat-off"
    WorkspaceManager(workspace).init_workspace(name="gw-proactive-chitchat-off")

    _write_proactive(
        workspace / "PROACTIVE.md",
        """{
  "version": 1,
  "enabled": true,
  "timezone": "UTC",
  "tasks": [
    {
      "id": "chitchat-ping",
      "kind": "once",
      "at": "2026-03-01T08:00:00+00:00",
      "session_key": "cli:legacy-memory",
      "target": {
        "channel": "feishu",
        "chat_id": "chat-target"
      },
      "chitchat_mode": true,
      "prompt": "Send a casual proactive ping."
    }
  ]
}""",
    )

    runtime = GatewayRuntime(provider=DummyProvider(), workspace=workspace, proactive_poll_sec=0.05)
    adapter = FakeFeishuSessionAdapter("feishu", proactive_chitchat_enabled=False)
    runtime.register_adapter(adapter)

    await runtime.start()
    await asyncio.sleep(0.25)
    await runtime.stop()

    assert adapter.sent == []

    state = load_runtime_state(workspace)
    assert state.tasks["chitchat-ping"].completed_at is not None

    chitchat_session = SessionManager(workspace, workspace.name).get_or_create(
        "feishu:chat-target__chitchat"
    )
    assert len(chitchat_session.messages) == 0
