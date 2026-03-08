"""Event types for the message bus."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass
class InboundMessage:
    """Message received from a channel or internal trigger."""

    channel: str  # telegram, discord, slack, whatsapp, system, cron
    sender_id: str  # User or source identifier
    chat_id: str  # Chat/session identifier
    content: str  # Message text
    timestamp: datetime = field(default_factory=datetime.now)
    media: list[str] = field(default_factory=list)  # Media file paths or URLs
    metadata: dict[str, Any] = field(default_factory=dict)  # Channel-specific data
    session_key_override: str | None = None  # Optional override for session grouping
    priority: Literal["normal", "high", "low"] = "normal"  # Message priority

    @property
    def session_key(self) -> str:
        """Unique key for session identification."""
        return self.session_key_override or f"{self.channel}:{self.chat_id}"


@dataclass
class OutboundMessage:
    """Message to send to a channel."""

    channel: str
    chat_id: str
    content: str
    reply_to: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: Literal["normal", "high", "low"] = "normal"


@dataclass
class ProactiveTask:
    """A proactive task scheduled for execution."""

    task_id: str
    trigger_type: Literal["time", "event", "condition"]
    trigger_config: dict[str, Any]  # Schedule, event pattern, or condition
    action: str  # What to do when triggered
    session_key: str  # Which session to use
    created_at: datetime = field(default_factory=datetime.now)
    last_run: datetime | None = None
    next_run: datetime | None = None
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
