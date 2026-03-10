"""Feishu channel adapter with webhook ingress and HTTP outbound send."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Mapping

import httpx

from atom_agent.bus.events import InboundMessage, OutboundMessage
from atom_agent.channels.base import ChannelAdapter, InboundCallback
from atom_agent.logging import get_logger

logger = get_logger("channels.feishu")

_DEFAULT_API_BASE = "https://open.feishu.cn/open-apis"


@dataclass(frozen=True)
class FeishuConfig:
    """Runtime configuration for Feishu channel adapter."""

    app_id: str
    app_secret: str
    verification_token: str | None = None
    signing_secret: str | None = None
    allow_user_ids: set[str] = field(default_factory=set)
    allow_group_chats: bool = True
    dedup_cache_size: int = 1024

    @classmethod
    def from_env(cls) -> "FeishuConfig":
        """Build config from environment variables."""
        import os

        allowlist_raw = os.environ.get("FEISHU_ALLOW_USER_IDS", "")
        allow_user_ids = {item.strip() for item in allowlist_raw.split(",") if item.strip()}

        allow_group_raw = os.environ.get("FEISHU_ALLOW_GROUP_CHATS", "true").strip().lower()
        allow_group_chats = allow_group_raw in {"1", "true", "yes", "on"}

        dedup_cache_size_raw = os.environ.get("FEISHU_DEDUP_CACHE_SIZE", "1024").strip()
        try:
            dedup_cache_size = int(dedup_cache_size_raw)
        except ValueError:
            dedup_cache_size = 1024

        return cls(
            app_id=os.environ.get("FEISHU_APP_ID", "").strip(),
            app_secret=os.environ.get("FEISHU_APP_SECRET", "").strip(),
            verification_token=os.environ.get("FEISHU_VERIFICATION_TOKEN", "").strip() or None,
            signing_secret=os.environ.get("FEISHU_SIGNING_SECRET", "").strip() or None,
            allow_user_ids=allow_user_ids,
            allow_group_chats=allow_group_chats,
            dedup_cache_size=dedup_cache_size,
        )


class FeishuConfigError(ValueError):
    """Raised when Feishu config is incomplete or invalid."""


class FeishuAdapter(ChannelAdapter):
    """Feishu adapter supporting webhook ingress and outbound message send."""

    def __init__(
        self,
        config: FeishuConfig,
        *,
        api_base: str = _DEFAULT_API_BASE,
        http_timeout_sec: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ):
        super().__init__("feishu")
        self.config = config
        self.api_base = api_base.rstrip("/")
        self.http_timeout_sec = http_timeout_sec
        self._on_inbound: InboundCallback | None = None
        self._running = False

        self._client = client
        self._owns_client = client is None

        self._access_token: str | None = None
        self._access_token_expire_monotonic = 0.0
        self._token_lock = asyncio.Lock()

        self._seen_ids: OrderedDict[str, None] = OrderedDict()

    def readiness_errors(self) -> list[str]:
        """Return readiness validation errors."""
        errors: list[str] = []
        if not self.config.app_id:
            errors.append("Missing FEISHU_APP_ID.")
        if not self.config.app_secret:
            errors.append("Missing FEISHU_APP_SECRET.")
        if self.config.dedup_cache_size <= 0:
            errors.append("FEISHU_DEDUP_CACHE_SIZE must be > 0.")
        return errors

    def validate_readiness(self) -> None:
        """Raise if adapter config is not ready."""
        errors = self.readiness_errors()
        if errors:
            raise FeishuConfigError(" ".join(errors))

    async def start(self, on_inbound: InboundCallback) -> None:
        """Start adapter runtime."""
        self.validate_readiness()
        self._on_inbound = on_inbound
        self._running = True
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.http_timeout_sec)
            self._owns_client = True
        logger.info("Feishu adapter started")

    async def stop(self) -> None:
        """Stop adapter runtime and release resources."""
        self._running = False
        self._on_inbound = None
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None
        self._owns_client = False
        logger.info("Feishu adapter stopped")

    async def send(self, message: OutboundMessage) -> None:
        """Send text message to Feishu chat."""
        client = await self._ensure_client()
        token = await self._get_tenant_access_token()
        payload = {
            "receive_id": message.chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": message.content}, ensure_ascii=False),
        }
        url = f"{self.api_base}/im/v1/messages?receive_id_type=chat_id"
        response = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu send failed: code={data.get('code')} msg={data.get('msg')}")

    async def handle_webhook_event(
        self,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Handle one webhook payload and publish inbound message through callback.

        Returns a small status object suitable for HTTP handler responses.
        """
        del headers  # Placeholder for optional signature validation support.

        challenge = payload.get("challenge")
        if isinstance(challenge, str):
            self._verify_token(payload)
            return {"challenge": challenge}

        self._verify_token(payload)

        header = payload.get("header")
        if not isinstance(header, Mapping):
            return {"status": "ignored", "reason": "missing_header"}

        event_id = _str_or_none(header.get("event_id"))
        if event_id and self._seen_before(event_id):
            return {"status": "duplicate", "event_id": event_id}

        event = payload.get("event")
        if not isinstance(event, Mapping):
            return {"status": "ignored", "reason": "missing_event"}

        message = event.get("message")
        if not isinstance(message, Mapping):
            return {"status": "ignored", "reason": "missing_message"}

        message_id = _str_or_none(message.get("message_id"))
        if message_id and self._seen_before(message_id):
            return {"status": "duplicate", "message_id": message_id}

        sender_id = _extract_sender_id(event)
        if self.config.allow_user_ids and sender_id not in self.config.allow_user_ids:
            return {"status": "ignored", "reason": "sender_not_allowed"}

        chat_type = _str_or_none(message.get("chat_type")) or "unknown"
        if chat_type != "p2p" and not self.config.allow_group_chats:
            return {"status": "ignored", "reason": "group_chat_not_allowed"}

        chat_id = _str_or_none(message.get("chat_id"))
        if not chat_id:
            return {"status": "ignored", "reason": "missing_chat_id"}

        message_type = (_str_or_none(message.get("message_type")) or "text").strip().lower()
        content = _extract_message_text(message_type=message_type, raw_content=message.get("content"))
        if not content:
            return {"status": "ignored", "reason": "empty_content"}

        inbound = InboundMessage(
            channel="feishu",
            sender_id=sender_id or "unknown",
            chat_id=chat_id,
            content=content,
            metadata={
                "event_id": event_id,
                "message_id": message_id,
                "chat_type": chat_type,
                "message_type": message_type,
            },
        )

        if self._on_inbound is not None:
            result = self._on_inbound(inbound)
            if inspect.isawaitable(result):
                await result
        else:
            logger.warning("Feishu webhook event received before adapter.start()")

        return {"status": "ok", "event_id": event_id, "message_id": message_id}

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.http_timeout_sec)
            self._owns_client = True
        return self._client

    async def _get_tenant_access_token(self) -> str:
        now = time.monotonic()
        if self._access_token and now < self._access_token_expire_monotonic - 30:
            return self._access_token

        async with self._token_lock:
            now = time.monotonic()
            if self._access_token and now < self._access_token_expire_monotonic - 30:
                return self._access_token

            client = await self._ensure_client()
            response = await client.post(
                f"{self.api_base}/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self.config.app_id,
                    "app_secret": self.config.app_secret,
                },
            )
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0:
                raise RuntimeError(
                    f"Failed to fetch Feishu tenant token: code={data.get('code')} msg={data.get('msg')}"
                )
            token = data.get("tenant_access_token")
            expire = int(data.get("expire", 7200))
            if not isinstance(token, str) or not token:
                raise RuntimeError("Feishu token response missing tenant_access_token.")

            self._access_token = token
            self._access_token_expire_monotonic = time.monotonic() + max(expire, 60)
            return token

    def _verify_token(self, payload: Mapping[str, Any]) -> None:
        expected = self.config.verification_token
        if not expected:
            return

        token = payload.get("token")
        if not isinstance(token, str) or not token:
            header = payload.get("header")
            if isinstance(header, Mapping):
                token = _str_or_none(header.get("token"))
        if token != expected:
            raise PermissionError("Feishu webhook verification token mismatch.")

    def _seen_before(self, value: str) -> bool:
        if not value:
            return False
        if value in self._seen_ids:
            return True
        self._seen_ids[value] = None
        while len(self._seen_ids) > self.config.dedup_cache_size:
            self._seen_ids.popitem(last=False)
        return False


def _extract_sender_id(event: Mapping[str, Any]) -> str:
    sender = event.get("sender")
    if not isinstance(sender, Mapping):
        return ""
    sender_id = sender.get("sender_id")
    if not isinstance(sender_id, Mapping):
        return ""
    for key in ("open_id", "union_id", "user_id"):
        value = _str_or_none(sender_id.get(key))
        if value:
            return value
    return ""


def _extract_message_text(message_type: str, raw_content: Any) -> str:
    if isinstance(raw_content, str):
        try:
            content = json.loads(raw_content)
        except json.JSONDecodeError:
            content = {"text": raw_content}
    elif isinstance(raw_content, Mapping):
        content = raw_content
    else:
        content = {}

    if message_type == "text":
        text = content.get("text")
        return text.strip() if isinstance(text, str) else ""

    if message_type == "post":
        return _extract_post_text(content)

    if message_type in {"image", "audio", "media", "file", "sticker"}:
        return f"[{message_type}]"

    return ""


def _extract_post_text(content: Mapping[str, Any]) -> str:
    def _extract_localized_block(data: Mapping[str, Any]) -> list[list[dict[str, Any]]]:
        if isinstance(data.get("content"), list):
            return [row for row in data["content"] if isinstance(row, list)]
        return []

    if "content" in content:
        rows = _extract_localized_block(content)
    else:
        post = content.get("post")
        if isinstance(post, Mapping):
            source = next((v for v in post.values() if isinstance(v, Mapping)), {})
        else:
            source = next((v for v in content.values() if isinstance(v, Mapping)), {})
        rows = _extract_localized_block(source) if isinstance(source, Mapping) else []

    parts: list[str] = []
    for row in rows:
        for item in row:
            if not isinstance(item, Mapping):
                continue
            tag = _str_or_none(item.get("tag")) or ""
            if tag in {"text", "a"}:
                text = _str_or_none(item.get("text"))
                if text:
                    parts.append(text)
            elif tag == "at":
                name = _str_or_none(item.get("user_name")) or "user"
                parts.append(f"@{name}")

    return " ".join(parts).strip()


def _str_or_none(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None
