"""Unit tests for proactive markdown parser/validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from atom_agent.proactive import (
    ProactiveValidationError,
    parse_proactive_file,
    parse_proactive_markdown,
)


def _wrap_json(json_payload: str) -> str:
    return textwrap.dedent(
        f"""
        # Proactive Configuration

        ```json
        {json_payload}
        ```
        """
    ).strip()


def test_parse_valid_markdown_with_defaults() -> None:
    markdown = _wrap_json(
        """{
  "version": 1,
  "enabled": true,
  "tasks": [
    {
      "id": "daily",
      "kind": "cron",
      "cron": "0 9 * * *",
      "session_key": "telegram:123",
      "prompt": "Say hi"
    }
  ]
}"""
    )

    config = parse_proactive_markdown(markdown)
    assert config.version == 1
    assert config.enabled is True
    assert config.timezone == "UTC"
    assert len(config.tasks) == 1
    assert config.tasks[0].enabled is True
    assert config.tasks[0].jitter_sec == 0


def test_parse_file_sets_source_path(tmp_path: Path) -> None:
    path = tmp_path / "PROACTIVE.md"
    path.write_text(
        _wrap_json(
            """{
  "version": 1,
  "enabled": false,
  "timezone": "UTC",
  "tasks": []
}"""
        ),
        encoding="utf-8",
    )

    config = parse_proactive_file(path)
    assert config.source_path == path
    assert config.tasks == []


def test_missing_json_block_is_rejected() -> None:
    with pytest.raises(ProactiveValidationError) as exc:
        parse_proactive_markdown("# Proactive\n\nNo JSON block here.")

    issue_codes = {issue.code for issue in exc.value.issues}
    assert "missing_json_block" in issue_codes


def test_duplicate_task_ids_are_rejected() -> None:
    markdown = _wrap_json(
        """{
  "version": 1,
  "enabled": true,
  "tasks": [
    {
      "id": "dup",
      "kind": "interval",
      "every_sec": 60,
      "session_key": "cli:1",
      "prompt": "Ping"
    },
    {
      "id": "dup",
      "kind": "interval",
      "every_sec": 120,
      "session_key": "cli:1",
      "prompt": "Ping again"
    }
  ]
}"""
    )

    with pytest.raises(ProactiveValidationError) as exc:
        parse_proactive_markdown(markdown)

    issue_codes = {issue.code for issue in exc.value.issues}
    assert "duplicate_id" in issue_codes


def test_once_requires_timezone_in_datetime() -> None:
    markdown = _wrap_json(
        """{
  "version": 1,
  "enabled": true,
  "tasks": [
    {
      "id": "wake",
      "kind": "once",
      "at": "2026-03-10T07:30:00",
      "session_key": "cli:abc",
      "prompt": "Wake up"
    }
  ]
}"""
    )

    with pytest.raises(ProactiveValidationError) as exc:
        parse_proactive_markdown(markdown)

    issue_codes = {issue.code for issue in exc.value.issues}
    assert "missing_timezone" in issue_codes


def test_parse_task_with_explicit_target() -> None:
    markdown = _wrap_json(
        """{
  "version": 1,
  "enabled": true,
  "timezone": "UTC",
  "tasks": [
    {
      "id": "route-explicit",
      "kind": "interval",
      "every_sec": 300,
      "session_key": "cli:memory-1",
      "target": {
        "channel": "feishu",
        "chat_id": "oc_xxx",
        "reply_to": "om_123"
      },
      "prompt": "Route using explicit target."
    }
  ]
}"""
    )

    config = parse_proactive_markdown(markdown)
    task = config.tasks[0]
    assert task.target is not None
    assert task.target.channel == "feishu"
    assert task.target.chat_id == "oc_xxx"
    assert task.target.reply_to == "om_123"
    assert task.target.thread_id is None


def test_target_unknown_field_is_rejected() -> None:
    markdown = _wrap_json(
        """{
  "version": 1,
  "enabled": true,
  "timezone": "UTC",
  "tasks": [
    {
      "id": "bad-target",
      "kind": "interval",
      "every_sec": 60,
      "session_key": "cli:abc",
      "target": {
        "channel": "feishu",
        "chat_id": "oc_xxx",
        "room": "foo"
      },
      "prompt": "Ping"
    }
  ]
}"""
    )

    with pytest.raises(ProactiveValidationError) as exc:
        parse_proactive_markdown(markdown)

    issue_codes = {issue.code for issue in exc.value.issues}
    assert "unknown_field" in issue_codes
