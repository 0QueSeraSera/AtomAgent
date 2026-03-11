"""Unit tests for proactive runtime dispatch helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from atom_agent.proactive.models import DueTask, ProactiveTarget
from atom_agent.proactive.runtime import (
    build_due_inbound_message,
    parse_session_key,
    resolve_due_target,
)


def _due_task(*, target: ProactiveTarget | None = None) -> DueTask:
    now = datetime(2026, 3, 10, 12, 0, tzinfo=ZoneInfo("UTC"))
    return DueTask(
        task_id="task-1",
        kind="once",
        session_key="cli:memory-1",
        prompt="Hello",
        target=target,
        scheduled_time=now,
        base_time=now,
    )


def test_parse_session_key() -> None:
    assert parse_session_key("feishu:oc_123") == ("feishu", "oc_123")
    assert parse_session_key("plain") == ("cli", "plain")


def test_resolve_due_target_uses_explicit_target() -> None:
    due = _due_task(target=ProactiveTarget(channel="feishu", chat_id="oc_123", reply_to="om_1"))
    channel, chat_id, metadata = resolve_due_target(due)
    assert channel == "feishu"
    assert chat_id == "oc_123"
    assert metadata["reply_to"] == "om_1"


def test_build_due_inbound_message_preserves_memory_scope() -> None:
    due = _due_task(target=ProactiveTarget(channel="feishu", chat_id="oc_123", thread_id="th_1"))
    msg = build_due_inbound_message(due)
    assert msg.channel == "system"
    assert msg.chat_id == "feishu:oc_123"
    assert msg.session_key_override == "cli:memory-1"
    assert msg.metadata["task_id"] == "task-1"
    assert msg.metadata["thread_id"] == "th_1"
