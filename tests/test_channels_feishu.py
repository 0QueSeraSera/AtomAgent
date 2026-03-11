"""Unit tests for Feishu channel adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

import atom_agent.channels.feishu as feishu_module
from atom_agent.bus.events import InboundMessage, OutboundMessage
from atom_agent.channels import FeishuAdapter, FeishuConfig, FeishuConfigError


@dataclass
class FakeResponse:
    payload: dict[str, Any]
    status_code: int = 200

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("POST", "https://example.invalid"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> dict[str, Any]:
        return self.payload


@dataclass
class FakeAsyncClient:
    token_calls: int = 0
    send_calls: int = 0
    last_send_payload: Mapping[str, Any] | None = None
    closed: bool = False
    requests: list[str] = field(default_factory=list)

    async def post(
        self,
        url: str,
        *,
        json: Mapping[str, Any] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> FakeResponse:
        del headers
        self.requests.append(url)
        if url.endswith("/auth/v3/tenant_access_token/internal"):
            self.token_calls += 1
            return FakeResponse({"code": 0, "tenant_access_token": "token-123", "expire": 7200})

        if "/im/v1/messages" in url:
            self.send_calls += 1
            self.last_send_payload = json
            return FakeResponse({"code": 0, "msg": "ok"})

        return FakeResponse({"code": 404, "msg": "unknown"}, status_code=404)

    async def aclose(self) -> None:
        self.closed = True


def _config(**kwargs: Any) -> FeishuConfig:
    base = {
        "app_id": "cli_demo",
        "app_secret": "sec_demo",
        "verification_token": "verify-123",
        "connection_mode": "webhook",
    }
    base.update(kwargs)
    return FeishuConfig(**base)


@pytest.mark.asyncio
async def test_feishu_adapter_requires_app_credentials() -> None:
    adapter = FeishuAdapter(FeishuConfig(app_id="", app_secret=""))
    with pytest.raises(FeishuConfigError):
        await adapter.start(lambda _: None)


@pytest.mark.asyncio
async def test_feishu_webhook_text_mapping_and_dedup() -> None:
    received: list[InboundMessage] = []
    adapter = FeishuAdapter(_config(), client=FakeAsyncClient())
    await adapter.start(received.append)

    payload = {
        "header": {
            "event_id": "evt-1",
            "token": "verify-123",
            "event_type": "im.message.receive_v1",
        },
        "event": {
            "sender": {"sender_id": {"open_id": "ou_user_1"}},
            "message": {
                "message_id": "om_1",
                "chat_id": "oc_chat_1",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "hello"}),
            },
        },
    }

    first = await adapter.handle_webhook_event(payload)
    second = await adapter.handle_webhook_event(payload)

    assert first["status"] == "ok"
    assert second["status"] == "duplicate"
    assert len(received) == 1
    assert received[0].channel == "feishu"
    assert received[0].chat_id == "oc_chat_1"
    assert received[0].sender_id == "ou_user_1"
    assert received[0].content == "hello"


@pytest.mark.asyncio
async def test_feishu_webhook_challenge_echo() -> None:
    adapter = FeishuAdapter(_config(), client=FakeAsyncClient())
    result = await adapter.handle_webhook_event({"challenge": "abc", "token": "verify-123"})
    assert result == {"challenge": "abc"}


@pytest.mark.asyncio
async def test_feishu_webhook_blocks_unallowlisted_sender() -> None:
    adapter = FeishuAdapter(
        _config(allow_user_ids={"ou_allowed"}),
        client=FakeAsyncClient(),
    )
    await adapter.start(lambda _: None)

    payload = {
        "header": {"event_id": "evt-2", "token": "verify-123"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_denied"}},
            "message": {
                "message_id": "om_2",
                "chat_id": "oc_chat_2",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "blocked"}),
            },
        },
    }
    result = await adapter.handle_webhook_event(payload)
    assert result["status"] == "ignored"
    assert result["reason"] == "sender_not_allowed"


@pytest.mark.asyncio
async def test_feishu_webhook_allowlist_accepts_user_id_when_open_id_present() -> None:
    adapter = FeishuAdapter(
        _config(allow_user_ids={"u_allowed"}),
        client=FakeAsyncClient(),
    )
    await adapter.start(lambda _: None)

    payload = {
        "header": {"event_id": "evt-3", "token": "verify-123"},
        "event": {
            "sender": {"sender_id": {"open_id": "ou_other", "user_id": "u_allowed"}},
            "message": {
                "message_id": "om_3",
                "chat_id": "oc_chat_3",
                "chat_type": "p2p",
                "message_type": "text",
                "content": json.dumps({"text": "allowed"}),
            },
        },
    }
    result = await adapter.handle_webhook_event(payload)
    assert result["status"] == "ok"


def test_feishu_readiness_long_connection_requires_lark_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(feishu_module, "_lark_sdk_available", lambda: False)
    adapter = FeishuAdapter(FeishuConfig(app_id="cli_demo", app_secret="sec_demo"))
    assert any("lark-oapi" in msg for msg in adapter.readiness_errors())


def test_feishu_readiness_webhook_mode_does_not_require_lark_sdk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(feishu_module, "_lark_sdk_available", lambda: False)
    adapter = FeishuAdapter(
        FeishuConfig(app_id="cli_demo", app_secret="sec_demo", connection_mode="webhook")
    )
    assert adapter.readiness_errors() == []


@pytest.mark.asyncio
async def test_feishu_send_fetches_token_and_reuses_cache() -> None:
    fake_client = FakeAsyncClient()
    adapter = FeishuAdapter(_config(), client=fake_client)
    await adapter.start(lambda _: None)

    outbound = OutboundMessage(channel="feishu", chat_id="oc_chat_3", content="hello outbound")
    await adapter.send(outbound)
    await adapter.send(outbound)

    assert fake_client.token_calls == 1
    assert fake_client.send_calls == 2
    assert fake_client.last_send_payload is not None
    assert fake_client.last_send_payload["receive_id"] == "oc_chat_3"
