"""Session routing logic for Feishu chitchat vs normal sessions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from atom_agent.logging import get_logger

logger = get_logger("channels.feishu_session")

# Session key prefixes
CHITCHAT_PREFIX = "feishu:chitchat:"
NORMAL_PREFIX = "feishu:"


@dataclass
class ChitchatSessionInfo:
    """Information about an active chitchat session."""

    chat_id: str
    started_at: datetime
    message_count: int = 0
    last_message_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class FeishuSessionRouter:
    """Routes Feishu messages to appropriate session based on chitchat state."""

    def __init__(self, *, chitchat_timeout_sec: int = 3600):
        """
        Initialize the session router.

        Args:
            chitchat_timeout_sec: Seconds after which chitchat session auto-expires
        """
        self._active_chitchats: dict[str, ChitchatSessionInfo] = {}
        self._chitchat_timeout_sec = chitchat_timeout_sec

    def get_session_key(
        self,
        chat_id: str,
        *,
        is_proactive: bool = False,
        force_chitchat: bool = False,
        force_normal: bool = False,
    ) -> str:
        """
        Return appropriate session key for routing.

        Args:
            chat_id: The Feishu chat ID
            is_proactive: Whether this is a proactive message
            force_chitchat: Force routing to chitchat session
            force_normal: Force routing to normal session

        Returns:
            Session key with appropriate prefix
        """
        # Explicit overrides
        if force_normal:
            return f"{NORMAL_PREFIX}{chat_id}"
        if force_chitchat:
            return f"{CHITCHAT_PREFIX}{chat_id}"

        # Check if currently in chitchat mode
        if self.is_in_chitchat(chat_id):
            return f"{CHITCHAT_PREFIX}{chat_id}"

        # Default to normal session
        return f"{NORMAL_PREFIX}{chat_id}"

    def is_in_chitchat(self, chat_id: str) -> bool:
        """
        Check if chat is currently in proactive chitchat mode.

        Args:
            chat_id: The Feishu chat ID

        Returns:
            True if in active chitchat session
        """
        info = self._active_chitchats.get(chat_id)
        if info is None:
            return False

        # Check for timeout
        if self._is_chitchat_expired(info):
            self.end_chitchat(chat_id)
            return False

        return True

    def start_chitchat(self, chat_id: str, metadata: dict[str, Any] | None = None) -> None:
        """
        Mark chat as in active chitchat mode.

        Args:
            chat_id: The Feishu chat ID
            metadata: Optional metadata for the session
        """
        now = datetime.now()
        info = ChitchatSessionInfo(
            chat_id=chat_id,
            started_at=now,
            last_message_at=now,
            metadata=metadata or {},
        )
        self._active_chitchats[chat_id] = info

        logger.info(
            "Chitchat session started",
            extra={
                "chat_id": chat_id,
                "session_key": f"{CHITCHAT_PREFIX}{chat_id}",
            },
        )

    def end_chitchat(self, chat_id: str) -> bool:
        """
        Mark chitchat as ended, revert to normal session.

        Args:
            chat_id: The Feishu chat ID

        Returns:
            True if there was an active chitchat to end
        """
        info = self._active_chitchats.pop(chat_id, None)
        if info is None:
            return False

        duration = datetime.now() - info.started_at
        logger.info(
            "Chitchat session ended",
            extra={
                "chat_id": chat_id,
                "message_count": info.message_count,
                "duration_sec": int(duration.total_seconds()),
            },
        )
        return True

    def record_chitchat_message(self, chat_id: str) -> None:
        """
        Record that a message was sent/received in chitchat mode.

        Args:
            chat_id: The Feishu chat ID
        """
        info = self._active_chitchats.get(chat_id)
        if info is not None:
            info.message_count += 1
            info.last_message_at = datetime.now()

    def get_chitchat_info(self, chat_id: str) -> ChitchatSessionInfo | None:
        """
        Get information about an active chitchat session.

        Args:
            chat_id: The Feishu chat ID

        Returns:
            ChitchatSessionInfo if active, None otherwise
        """
        info = self._active_chitchats.get(chat_id)
        if info is not None and not self._is_chitchat_expired(info):
            return info
        return None

    def parse_session_key(self, session_key: str) -> tuple[str, str, bool]:
        """
        Parse a session key into components.

        Args:
            session_key: The session key to parse

        Returns:
            Tuple of (channel, chat_id, is_chitchat)
        """
        if session_key.startswith(CHITCHAT_PREFIX):
            chat_id = session_key[len(CHITCHAT_PREFIX) :]
            return "feishu", chat_id, True
        elif session_key.startswith(NORMAL_PREFIX):
            chat_id = session_key[len(NORMAL_PREFIX) :]
            return "feishu", chat_id, False
        else:
            # Fallback for other formats
            if ":" in session_key:
                channel, chat_id = session_key.split(":", 1)
                return channel, chat_id, False
            return "feishu", session_key, False

    def _is_chitchat_expired(self, info: ChitchatSessionInfo) -> bool:
        """Check if chitchat session has expired due to timeout."""
        if self._chitchat_timeout_sec <= 0:
            return False  # No timeout

        last_activity = info.last_message_at or info.started_at
        elapsed = (datetime.now() - last_activity).total_seconds()
        return elapsed > self._chitchat_timeout_sec

    def cleanup_expired(self) -> int:
        """
        Clean up expired chitchat sessions.

        Returns:
            Number of sessions cleaned up
        """
        expired_chats = [
            chat_id
            for chat_id, info in self._active_chitchats.items()
            if self._is_chitchat_expired(info)
        ]

        for chat_id in expired_chats:
            self.end_chitchat(chat_id)

        if expired_chats:
            logger.info(
                "Cleaned up expired chitchat sessions",
                extra={"count": len(expired_chats)},
            )

        return len(expired_chats)

    @property
    def active_chitchat_count(self) -> int:
        """Return count of active chitchat sessions."""
        return len(self._active_chitchats)

    def get_all_active_chitchats(self) -> dict[str, ChitchatSessionInfo]:
        """Return copy of all active chitchat sessions."""
        return dict(self._active_chitchats)


def is_chitchat_session_key(session_key: str) -> bool:
    """
    Check if a session key is for a chitchat session.

    Args:
        session_key: The session key to check

    Returns:
        True if it's a chitchat session key
    """
    return session_key.startswith(CHITCHAT_PREFIX)


def make_chitchat_session_key(chat_id: str) -> str:
    """
    Create a chitchat session key from a chat ID.

    Args:
        chat_id: The Feishu chat ID

    Returns:
        Chitchat session key
    """
    return f"{CHITCHAT_PREFIX}{chat_id}"


def make_normal_session_key(chat_id: str) -> str:
    """
    Create a normal session key from a chat ID.

    Args:
        chat_id: The Feishu chat ID

    Returns:
        Normal session key
    """
    return f"{NORMAL_PREFIX}{chat_id}"
