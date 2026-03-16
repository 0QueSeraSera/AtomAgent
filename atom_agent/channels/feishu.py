"""Feishu channel adapter with long-connection ingress and HTTP outbound send."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import inspect
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Mapping

import httpx

from atom_agent.bus.events import InboundMessage, OutboundMessage
from atom_agent.channels.base import ChannelAdapter, InboundCallback
from atom_agent.logging import get_logger

if TYPE_CHECKING:
    from atom_agent.channels.feishu_session import FeishuSessionRouter

logger = get_logger("channels.feishu")

_DEFAULT_API_BASE = "https://open.feishu.cn/open-apis"
_CONNECTION_MODES = {"long_connection", "webhook"}


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
    connection_mode: str = "long_connection"

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

        connection_mode_raw = os.environ.get("FEISHU_CONNECTION_MODE", "long_connection").strip()
        connection_mode = _normalize_connection_mode(connection_mode_raw)

        return cls(
            app_id=os.environ.get("FEISHU_APP_ID", "").strip(),
            app_secret=os.environ.get("FEISHU_APP_SECRET", "").strip(),
            verification_token=os.environ.get("FEISHU_VERIFICATION_TOKEN", "").strip() or None,
            signing_secret=os.environ.get("FEISHU_SIGNING_SECRET", "").strip() or None,
            allow_user_ids=allow_user_ids,
            allow_group_chats=allow_group_chats,
            dedup_cache_size=dedup_cache_size,
            connection_mode=connection_mode,
        )


class FeishuConfigError(ValueError):
    """Raised when Feishu config is incomplete or invalid."""


class FeishuAdapter(ChannelAdapter):
    """Feishu adapter supporting long-connection/webhook ingress and HTTP outbound send."""

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
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._ws_stop = threading.Event()

        self._access_token: str | None = None
        self._access_token_expire_monotonic = 0.0
        self._token_lock = asyncio.Lock()

        self._seen_ids: OrderedDict[str, None] = OrderedDict()

        # Session router for chitchat/normal routing
        self._session_router: FeishuSessionRouter | None = None

    def readiness_errors(self) -> list[str]:
        """Return readiness validation errors."""
        errors: list[str] = []
        if not self.config.app_id:
            errors.append("Missing FEISHU_APP_ID.")
        if not self.config.app_secret:
            errors.append("Missing FEISHU_APP_SECRET.")
        if self.config.dedup_cache_size <= 0:
            errors.append("FEISHU_DEDUP_CACHE_SIZE must be > 0.")
        if self.config.connection_mode not in _CONNECTION_MODES:
            modes = ", ".join(sorted(_CONNECTION_MODES))
            errors.append(f"FEISHU_CONNECTION_MODE must be one of: {modes}.")
        if self.config.connection_mode == "long_connection" and not _lark_sdk_available():
            errors.append(
                "Missing dependency `lark-oapi` for Feishu long connection. Install with: pip install lark-oapi."
            )
        return errors

    def validate_readiness(self) -> None:
        """Raise if adapter config is not ready."""
        errors = self.readiness_errors()
        if errors:
            raise FeishuConfigError(" ".join(errors))

    def set_session_router(self, router: FeishuSessionRouter) -> None:
        """Attach session router for chitchat/normal routing."""
        self._session_router = router
        logger.info("Feishu session router attached")

    async def start(self, on_inbound: InboundCallback) -> None:
        """Start adapter runtime."""
        self.validate_readiness()
        self._on_inbound = on_inbound
        self._running = True
        self._loop = asyncio.get_running_loop()
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.http_timeout_sec)
            self._owns_client = True
        if self.config.connection_mode == "long_connection":
            self._start_long_connection()
        logger.info("Feishu adapter started", extra={"mode": self.config.connection_mode})

    async def stop(self) -> None:
        """Stop adapter runtime and release resources."""
        self._running = False
        self._ws_stop.set()
        if self._ws_thread is not None:
            self._ws_thread.join(timeout=0.2)
            self._ws_thread = None
        self._ws_client = None
        self._loop = None
        self._on_inbound = None
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None
        self._owns_client = False
        logger.info("Feishu adapter stopped")

    async def send(self, message: OutboundMessage) -> None:
        """Send text message to Feishu chat."""
        metadata = message.metadata if isinstance(message.metadata, dict) else {}
        # Chitchat proactive pushes are user-controlled via /proactive_chitchat_on/off.
        if (
            metadata.get("proactive")
            and metadata.get("chitchat_mode")
            and self._session_router is not None
            and not self._session_router.is_proactive_chitchat_enabled(message.chat_id)
        ):
            logger.info(
                "Suppressing Feishu chitchat proactive message while proactive chitchat is off",
                extra={"chat_id": message.chat_id, "task_id": metadata.get("task_id")},
            )
            return

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

        sender_ids = _extract_sender_ids(event)
        sender_id = sender_ids[0] if sender_ids else ""
        if self.config.allow_user_ids and not any(
            sender in self.config.allow_user_ids for sender in sender_ids
        ):
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

        # Build base metadata
        base_metadata = {
            "event_id": event_id,
            "message_id": message_id,
            "chat_type": chat_type,
            "message_type": message_type,
            "sender_ids": sender_ids,
        }

        # Route through session router
        session_key, routed_metadata = self._route_inbound_message(chat_id, content, base_metadata)

        inbound = InboundMessage(
            channel="feishu",
            sender_id=sender_id or "unknown",
            chat_id=chat_id,
            content=content,
            metadata=routed_metadata,
            session_key_override=session_key,
        )

        await self._publish_inbound(inbound, source="webhook")

        return {"status": "ok", "event_id": event_id, "message_id": message_id}

    def _route_inbound_message(
        self,
        chat_id: str,
        content: str,
        base_metadata: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """
        Route inbound message through session router if available.

        Args:
            chat_id: The Feishu chat ID
            content: The message content
            base_metadata: Base metadata for the message

        Returns:
            Tuple of (session_key, modified_metadata)
        """
        metadata = dict(base_metadata)
        metadata["feishu_chat_id"] = chat_id

        # Route through session router if available
        if self._session_router is not None:
            self._session_router.cleanup_expired()
            command_result = self._session_router.handle_command(chat_id, content)
            if command_result is not None:
                metadata.update(command_result.metadata)
                return command_result.session_key, metadata

            session_key = self._session_router.get_session_key(chat_id)
            if self._session_router.is_in_chitchat(chat_id):
                metadata["chitchat_active"] = True
                metadata["feishu_chitchat_session_key"] = self._session_router.get_chitchat_session_key(
                    chat_id
                )
                self._session_router.record_chitchat_message(chat_id)
            metadata["feishu_active_session_key"] = self._session_router.get_active_normal_session_key(
                chat_id
            )
            return session_key, metadata

        # Default routing without session router
        return f"feishu:{chat_id}", metadata

    def resolve_proactive_session_key(
        self,
        *,
        chat_id: str,
        chitchat_mode: bool,
    ) -> str | None:
        """
        Resolve Feishu proactive memory session key for one outbound target.

        Returns None when chitchat-mode proactive delivery is disabled by user command.
        """
        if self._session_router is None:
            return f"feishu:{chat_id}"
        if chitchat_mode:
            if not self._session_router.is_proactive_chitchat_enabled(chat_id):
                return None
            return self._session_router.get_chitchat_session_key(chat_id)
        return self._session_router.get_active_normal_session_key(chat_id)

    async def _publish_inbound(self, inbound: InboundMessage, *, source: str) -> None:
        if self._on_inbound is not None:
            result = self._on_inbound(inbound)
            if inspect.isawaitable(result):
                await result
            return
        logger.warning("Feishu inbound event received before adapter.start()", extra={"source": source})

    def _start_long_connection(self) -> None:
        lark = _import_lark()
        builder = lark.EventDispatcherHandler.builder("", self.config.verification_token or "")
        register = getattr(builder, "register_p2_im_message_receive_v1", None)
        if not callable(register):
            raise FeishuConfigError("Installed lark-oapi SDK does not support message receive event dispatch.")

        event_handler = register(self._on_long_connection_message_sync).build()
        self._ws_client = lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        self._ws_stop.clear()
        self._ws_thread = threading.Thread(target=self._run_ws_forever, daemon=True, name="feishu-ws")
        self._ws_thread.start()
        logger.info("Feishu long connection started")

    def _run_ws_forever(self) -> None:
        ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(ws_loop)
        try:
            ws_client_module = importlib.import_module("lark_oapi.ws.client")
            ws_client_module.loop = ws_loop
        except Exception:
            logger.warning("Failed to patch lark websocket event loop")

        try:
            while self._running and not self._ws_stop.is_set():
                try:
                    self._ws_client.start()
                except Exception as err:
                    if not self._running or self._ws_stop.is_set():
                        break
                    logger.warning("Feishu long connection dropped", extra={"error": str(err)})
                    self._ws_stop.wait(timeout=3.0)
        finally:
            ws_loop.close()

    def _on_long_connection_message_sync(self, data: Any) -> None:
        if self._loop is None or not self._loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(self._handle_long_connection_message(data), self._loop)
        future.add_done_callback(_log_future_error)

    async def _handle_long_connection_message(self, data: Any) -> None:
        event = _obj_get(data, "event")
        message = _obj_get(event, "message")
        if message is None:
            return

        message_id = _str_or_none(_obj_get(message, "message_id"))
        if message_id and self._seen_before(message_id):
            return

        sender = _obj_get(event, "sender")
        sender_type = (_str_or_none(_obj_get(sender, "sender_type")) or "").lower()
        if sender_type == "bot":
            return

        sender_ids = _extract_sender_ids(event)
        sender_id = sender_ids[0] if sender_ids else ""
        if self.config.allow_user_ids and not any(
            sender in self.config.allow_user_ids for sender in sender_ids
        ):
            return

        chat_type = _str_or_none(_obj_get(message, "chat_type")) or "unknown"
        if chat_type != "p2p" and not self.config.allow_group_chats:
            return

        chat_id = _str_or_none(_obj_get(message, "chat_id"))
        if not chat_id:
            return

        message_type = (_str_or_none(_obj_get(message, "message_type")) or "text").strip().lower()
        content = _extract_message_text(message_type=message_type, raw_content=_obj_get(message, "content"))
        if not content:
            return

        # Build base metadata
        base_metadata = {
            "message_id": message_id,
            "chat_type": chat_type,
            "message_type": message_type,
            "sender_ids": sender_ids,
        }

        # Route through session router
        session_key, routed_metadata = self._route_inbound_message(chat_id, content, base_metadata)

        inbound = InboundMessage(
            channel="feishu",
            sender_id=sender_id or "unknown",
            chat_id=chat_id,
            content=content,
            metadata=routed_metadata,
            session_key_override=session_key,
        )
        await self._publish_inbound(inbound, source="long_connection")

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

def _extract_sender_ids(event: Any) -> list[str]:
    sender = _obj_get(event, "sender")
    sender_id = _obj_get(sender, "sender_id")
    candidates: list[str] = []
    for key in ("open_id", "union_id", "user_id"):
        value = _str_or_none(_obj_get(sender_id, key))
        if value:
            candidates.append(value)
    return list(dict.fromkeys(candidates))


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


def _obj_get(container: Any, key: str) -> Any:
    if isinstance(container, Mapping):
        return container.get(key)
    return getattr(container, key, None)


def _normalize_connection_mode(mode: str) -> str:
    clean = mode.strip().lower().replace("-", "_")
    if clean in {"websocket", "ws", "long"}:
        return "long_connection"
    if clean in {"http"}:
        return "webhook"
    if clean in _CONNECTION_MODES:
        return clean
    return "long_connection"


def _lark_sdk_available() -> bool:
    return importlib.util.find_spec("lark_oapi") is not None


def _import_lark() -> Any:
    return importlib.import_module("lark_oapi")


def _log_future_error(future: Any) -> None:
    try:
        future.result()
    except Exception as err:
        logger.error("Feishu long-connection event handler failed", extra={"error": str(err)})
