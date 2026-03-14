"""Session routing and command state for Feishu sessions."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from atom_agent.logging import get_logger

logger = get_logger("channels.feishu_session")

# Canonical session key patterns
NORMAL_PREFIX = "feishu:"
_SESSION_SEP = "__"
CHITCHAT_SESSION_ID = "chitchat"
DEFAULT_SESSION_ID = "default"

# Legacy pattern kept for backwards parsing compatibility.
LEGACY_CHITCHAT_PREFIX = "feishu:chitchat:"


@dataclass
class ChitchatSessionInfo:
    """Information about an active chitchat session."""

    chat_id: str
    started_at: datetime
    message_count: int = 0
    last_message_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeishuCommandResult:
    """Structured result for command-based routing decisions."""

    command: str
    session_key: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FeishuChatSessionState:
    """Persisted routing state for one Feishu chat."""

    chat_id: str
    active_normal_session_id: str = DEFAULT_SESSION_ID
    known_normal_session_ids: list[str] = field(default_factory=lambda: [DEFAULT_SESSION_ID])
    chitchat_enabled: bool = False
    chitchat_started_at: str | None = None
    chitchat_last_message_at: str | None = None
    chitchat_message_count: int = 0
    chitchat_metadata: dict[str, Any] = field(default_factory=dict)

    def normalize(self) -> None:
        """Repair incomplete state payloads from older versions."""
        if not self.active_normal_session_id:
            self.active_normal_session_id = DEFAULT_SESSION_ID
        cleaned = [item.strip() for item in self.known_normal_session_ids if isinstance(item, str)]
        dedup: list[str] = []
        for session_id in cleaned:
            if session_id and session_id not in dedup:
                dedup.append(session_id)
        if DEFAULT_SESSION_ID not in dedup:
            dedup.insert(0, DEFAULT_SESSION_ID)
        if self.active_normal_session_id not in dedup:
            dedup.append(self.active_normal_session_id)
        self.known_normal_session_ids = dedup

    def to_dict(self) -> dict[str, Any]:
        return {
            "chat_id": self.chat_id,
            "active_normal_session_id": self.active_normal_session_id,
            "known_normal_session_ids": list(self.known_normal_session_ids),
            "chitchat_enabled": self.chitchat_enabled,
            "chitchat_started_at": self.chitchat_started_at,
            "chitchat_last_message_at": self.chitchat_last_message_at,
            "chitchat_message_count": self.chitchat_message_count,
            "chitchat_metadata": dict(self.chitchat_metadata),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "FeishuChatSessionState":
        state = cls(
            chat_id=str(raw.get("chat_id", "")).strip(),
            active_normal_session_id=str(raw.get("active_normal_session_id", DEFAULT_SESSION_ID)).strip()
            or DEFAULT_SESSION_ID,
            known_normal_session_ids=list(raw.get("known_normal_session_ids", [DEFAULT_SESSION_ID])),
            chitchat_enabled=bool(raw.get("chitchat_enabled", False)),
            chitchat_started_at=raw.get("chitchat_started_at"),
            chitchat_last_message_at=raw.get("chitchat_last_message_at"),
            chitchat_message_count=int(raw.get("chitchat_message_count", 0) or 0),
            chitchat_metadata=(
                dict(raw.get("chitchat_metadata"))
                if isinstance(raw.get("chitchat_metadata"), dict)
                else {}
            ),
        )
        state.normalize()
        return state


class FeishuSessionRouter:
    """Routes Feishu messages to active normal/chitchat sessions."""

    def __init__(
        self,
        *,
        workspace: Path | None = None,
        state_path: Path | None = None,
        chitchat_timeout_sec: int = 0,
    ):
        self._chats: dict[str, FeishuChatSessionState] = {}
        self._chitchat_timeout_sec = max(0, int(chitchat_timeout_sec))
        self._state_path = state_path
        if self._state_path is None and workspace is not None:
            self._state_path = workspace / ".feishu_sessions.json"
        self._load_state()

    @property
    def state_path(self) -> Path | None:
        return self._state_path

    def _load_state(self) -> None:
        path = self._state_path
        if path is None or not path.exists():
            return

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            chats = data.get("chats", {}) if isinstance(data, dict) else {}
            if not isinstance(chats, dict):
                return
            loaded: dict[str, FeishuChatSessionState] = {}
            for chat_id, raw_state in chats.items():
                if not isinstance(raw_state, dict):
                    continue
                parsed = FeishuChatSessionState.from_dict({"chat_id": chat_id, **raw_state})
                if parsed.chat_id:
                    loaded[parsed.chat_id] = parsed
            self._chats = loaded
            if loaded:
                logger.info(
                    "Feishu session state loaded",
                    extra={"path": str(path), "chat_count": len(loaded)},
                )
        except Exception as err:
            logger.warning(
                "Failed to load Feishu session state",
                extra={"path": str(path), "error": str(err)},
            )

    def _save_state(self) -> None:
        path = self._state_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": 1,
                "updated_at": datetime.now().isoformat(),
                "chats": {chat_id: state.to_dict() for chat_id, state in self._chats.items()},
            }
            tmp_path = path.with_suffix(path.suffix + ".tmp")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(path)
        except Exception as err:
            logger.warning(
                "Failed to persist Feishu session state",
                extra={"path": str(path), "error": str(err)},
            )

    def _ensure_state(self, chat_id: str) -> FeishuChatSessionState:
        state = self._chats.get(chat_id)
        if state is None:
            state = FeishuChatSessionState(chat_id=chat_id)
            state.normalize()
            self._chats[chat_id] = state
            self._save_state()
        return state

    def _register_session_id(self, chat_id: str, session_id: str, *, set_active: bool = False) -> None:
        state = self._ensure_state(chat_id)
        if session_id not in state.known_normal_session_ids:
            state.known_normal_session_ids.append(session_id)
        if set_active:
            state.active_normal_session_id = session_id
        state.normalize()
        self._save_state()

    def _mark_chitchat_activity(self, state: FeishuChatSessionState) -> None:
        now_text = datetime.now().isoformat()
        if state.chitchat_started_at is None:
            state.chitchat_started_at = now_text
        state.chitchat_last_message_at = now_text

    def _is_chitchat_expired(self, state: FeishuChatSessionState) -> bool:
        if self._chitchat_timeout_sec <= 0:
            return False
        if not state.chitchat_last_message_at:
            return False
        try:
            last = datetime.fromisoformat(state.chitchat_last_message_at)
        except ValueError:
            return False
        elapsed = (datetime.now() - last).total_seconds()
        return elapsed > self._chitchat_timeout_sec

    def get_session_key(
        self,
        chat_id: str,
        *,
        force_chitchat: bool = False,
        force_normal: bool = False,
    ) -> str:
        """Return active session key for one chat."""
        state = self._ensure_state(chat_id)
        if force_normal:
            return make_normal_session_key(chat_id, state.active_normal_session_id)
        if force_chitchat:
            return make_chitchat_session_key(chat_id)

        if self.is_in_chitchat(chat_id):
            return make_chitchat_session_key(chat_id)
        return make_normal_session_key(chat_id, state.active_normal_session_id)

    def get_active_normal_session_key(self, chat_id: str) -> str:
        state = self._ensure_state(chat_id)
        return make_normal_session_key(chat_id, state.active_normal_session_id)

    def get_active_normal_session_id(self, chat_id: str) -> str:
        return self._ensure_state(chat_id).active_normal_session_id

    def get_chitchat_session_key(self, chat_id: str) -> str:
        return make_chitchat_session_key(chat_id)

    def list_normal_session_ids(self, chat_id: str) -> list[str]:
        state = self._ensure_state(chat_id)
        return list(state.known_normal_session_ids)

    def start_new_normal_session(self, chat_id: str, *, session_id: str | None = None) -> str:
        """Create and activate a new normal session."""
        new_id = session_id.strip() if isinstance(session_id, str) else ""
        if not new_id:
            new_id = str(uuid.uuid4())
        self._register_session_id(chat_id, new_id, set_active=True)
        logger.info(
            "Feishu normal session started",
            extra={"chat_id": chat_id, "session_id": new_id},
        )
        return make_normal_session_key(chat_id, new_id)

    def resume_normal_session(self, chat_id: str, session_id_or_key: str) -> str | None:
        """Activate a known normal session by id or full session key."""
        raw = session_id_or_key.strip()
        if not raw:
            return None

        session_id = raw
        if raw.startswith(NORMAL_PREFIX):
            parsed_channel, parsed_chat_id, is_chitchat, parsed_session_id = self.parse_session_key(raw)
            if parsed_channel != "feishu" or parsed_chat_id != chat_id or is_chitchat:
                return None
            session_id = parsed_session_id or DEFAULT_SESSION_ID

        state = self._ensure_state(chat_id)
        if session_id not in state.known_normal_session_ids:
            return None

        state.active_normal_session_id = session_id
        state.normalize()
        self._save_state()
        logger.info(
            "Feishu session resumed",
            extra={"chat_id": chat_id, "session_id": session_id},
        )
        return make_normal_session_key(chat_id, session_id)

    def is_in_chitchat(self, chat_id: str) -> bool:
        state = self._ensure_state(chat_id)
        if not state.chitchat_enabled:
            return False
        if self._is_chitchat_expired(state):
            self.end_chitchat(chat_id)
            return False
        return True

    def start_chitchat(self, chat_id: str, metadata: dict[str, Any] | None = None) -> None:
        state = self._ensure_state(chat_id)
        state.chitchat_enabled = True
        if metadata:
            state.chitchat_metadata = dict(metadata)
        self._mark_chitchat_activity(state)
        self._save_state()
        logger.info(
            "Feishu chitchat enabled",
            extra={"chat_id": chat_id, "session_key": make_chitchat_session_key(chat_id)},
        )

    def end_chitchat(self, chat_id: str) -> bool:
        state = self._ensure_state(chat_id)
        if not state.chitchat_enabled:
            return False
        state.chitchat_enabled = False
        self._save_state()
        logger.info("Feishu chitchat disabled", extra={"chat_id": chat_id})
        return True

    def record_chitchat_message(self, chat_id: str) -> None:
        state = self._ensure_state(chat_id)
        if not state.chitchat_enabled:
            return
        state.chitchat_message_count += 1
        self._mark_chitchat_activity(state)
        self._save_state()

    def get_chitchat_info(self, chat_id: str) -> ChitchatSessionInfo | None:
        state = self._ensure_state(chat_id)
        if not self.is_in_chitchat(chat_id):
            return None

        started = datetime.now()
        if state.chitchat_started_at:
            try:
                started = datetime.fromisoformat(state.chitchat_started_at)
            except ValueError:
                pass

        last_message_at = None
        if state.chitchat_last_message_at:
            try:
                last_message_at = datetime.fromisoformat(state.chitchat_last_message_at)
            except ValueError:
                last_message_at = None

        return ChitchatSessionInfo(
            chat_id=chat_id,
            started_at=started,
            message_count=state.chitchat_message_count,
            last_message_at=last_message_at,
            metadata=dict(state.chitchat_metadata),
        )

    def handle_command(self, chat_id: str, content: str) -> FeishuCommandResult | None:
        """Apply Feishu session command and return routing result."""
        tokens = content.strip().split()
        if not tokens:
            return None

        cmd = tokens[0].lower()
        base_meta: dict[str, Any] = {
            "feishu_chat_id": chat_id,
            "feishu_command": cmd,
            "feishu_active_session_key": self.get_active_normal_session_key(chat_id),
        }

        if cmd == "/new":
            session_key = self.start_new_normal_session(chat_id)
            _, _, _, session_id = self.parse_session_key(session_key)
            return FeishuCommandResult(
                command=cmd,
                session_key=session_key,
                metadata={
                    **base_meta,
                    "feishu_new_session": True,
                    "feishu_session_key": session_key,
                    "feishu_session_id": session_id,
                    "feishu_active_session_key": session_key,
                },
            )

        if cmd == "/sessions":
            return FeishuCommandResult(
                command=cmd,
                session_key=self.get_active_normal_session_key(chat_id),
                metadata={
                    **base_meta,
                    "feishu_sessions_request": True,
                    "feishu_known_session_ids": self.list_normal_session_ids(chat_id),
                },
            )

        if cmd == "/resume":
            if len(tokens) < 2:
                return FeishuCommandResult(
                    command=cmd,
                    session_key=self.get_active_normal_session_key(chat_id),
                    metadata={
                        **base_meta,
                        "feishu_resume_ok": False,
                        "feishu_resume_error": "Usage: /resume <session-id|session-key>",
                    },
                )

            resumed_key = self.resume_normal_session(chat_id, tokens[1])
            if resumed_key is None:
                return FeishuCommandResult(
                    command=cmd,
                    session_key=self.get_active_normal_session_key(chat_id),
                    metadata={
                        **base_meta,
                        "feishu_resume_ok": False,
                        "feishu_resume_error": f"Session not found: {tokens[1]}",
                    },
                )

            _, _, _, session_id = self.parse_session_key(resumed_key)
            return FeishuCommandResult(
                command=cmd,
                session_key=resumed_key,
                metadata={
                    **base_meta,
                    "feishu_resume_ok": True,
                    "feishu_session_key": resumed_key,
                    "feishu_session_id": session_id,
                    "feishu_active_session_key": resumed_key,
                },
            )

        if cmd == "/chitchat_on":
            self.start_chitchat(chat_id)
            return FeishuCommandResult(
                command=cmd,
                session_key=self.get_active_normal_session_key(chat_id),
                metadata={
                    **base_meta,
                    "chitchat_active": True,
                    "chitchat_turned_on": True,
                    "feishu_chitchat_session_key": make_chitchat_session_key(chat_id),
                },
            )

        if cmd in {"/chitchat_off", "/next_time"}:
            ended = self.end_chitchat(chat_id)
            return FeishuCommandResult(
                command=cmd,
                session_key=self.get_active_normal_session_key(chat_id),
                metadata={
                    **base_meta,
                    "chitchat_active": False,
                    "chitchat_ended": ended,
                    "chitchat_turned_off": True,
                    "feishu_next_time_alias": (cmd == "/next_time"),
                },
            )

        return None

    def parse_session_key(self, session_key: str) -> tuple[str, str, bool, str | None]:
        """Parse session key into (channel, chat_id, is_chitchat, session_id)."""
        if session_key.startswith(LEGACY_CHITCHAT_PREFIX):
            chat_id = session_key[len(LEGACY_CHITCHAT_PREFIX) :]
            return "feishu", chat_id, True, CHITCHAT_SESSION_ID

        if session_key.startswith(NORMAL_PREFIX):
            payload = session_key[len(NORMAL_PREFIX) :]
            if _SESSION_SEP in payload:
                chat_id, session_id = payload.split(_SESSION_SEP, 1)
                is_chitchat = session_id == CHITCHAT_SESSION_ID
                return "feishu", chat_id, is_chitchat, session_id
            return "feishu", payload, False, DEFAULT_SESSION_ID

        if ":" in session_key:
            channel, chat_id = session_key.split(":", 1)
            return channel, chat_id, False, None
        return "feishu", session_key, False, None

    def cleanup_expired(self) -> int:
        """Disable expired chitchat sessions and return cleaned count."""
        expired_count = 0
        for chat_id, state in list(self._chats.items()):
            if state.chitchat_enabled and self._is_chitchat_expired(state):
                state.chitchat_enabled = False
                expired_count += 1
        if expired_count:
            self._save_state()
            logger.info(
                "Feishu chitchat sessions expired",
                extra={"count": expired_count},
            )
        return expired_count

    @property
    def active_chitchat_count(self) -> int:
        """Return count of currently enabled chitchat sessions."""
        return sum(1 for state in self._chats.values() if state.chitchat_enabled)

    def get_all_active_chitchats(self) -> dict[str, ChitchatSessionInfo]:
        """Return active chitchat infos by chat id."""
        out: dict[str, ChitchatSessionInfo] = {}
        for chat_id in self._chats:
            info = self.get_chitchat_info(chat_id)
            if info is not None:
                out[chat_id] = info
        return out


def is_chitchat_session_key(session_key: str) -> bool:
    """Return True when session key points to chitchat scope."""
    if session_key.startswith(LEGACY_CHITCHAT_PREFIX):
        return True
    if not session_key.startswith(NORMAL_PREFIX):
        return False
    payload = session_key[len(NORMAL_PREFIX) :]
    if _SESSION_SEP not in payload:
        return False
    _chat_id, session_id = payload.split(_SESSION_SEP, 1)
    return session_id == CHITCHAT_SESSION_ID


def make_normal_session_key(chat_id: str, session_id: str = DEFAULT_SESSION_ID) -> str:
    """Create a normal Feishu session key."""
    clean_session_id = (session_id or DEFAULT_SESSION_ID).strip() or DEFAULT_SESSION_ID
    if clean_session_id == DEFAULT_SESSION_ID:
        return f"{NORMAL_PREFIX}{chat_id}"
    return f"{NORMAL_PREFIX}{chat_id}{_SESSION_SEP}{clean_session_id}"


def make_chitchat_session_key(chat_id: str) -> str:
    """Create a dedicated Feishu chitchat session key."""
    return f"{NORMAL_PREFIX}{chat_id}{_SESSION_SEP}{CHITCHAT_SESSION_ID}"
