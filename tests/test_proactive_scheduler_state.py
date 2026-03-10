"""Unit tests for proactive scheduler and runtime state persistence."""

from __future__ import annotations

from datetime import datetime, timedelta
from random import Random
from zoneinfo import ZoneInfo

from atom_agent.proactive import (
    ProactiveRuntimeState,
    evaluate_due_tasks,
    mark_task_finished,
    mark_task_started,
    parse_proactive_markdown,
)
from atom_agent.proactive.state import load_runtime_state, save_runtime_state


def _config(markdown_json: str):
    return parse_proactive_markdown(f"# Proactive\n\n```json\n{markdown_json}\n```")


def test_runtime_state_roundtrip(tmp_path):
    state = ProactiveRuntimeState()
    task = state.get_or_create_task("daily")
    task.status = "running"
    task.last_status = "success"
    task.last_run = datetime(2026, 3, 9, 10, 0, tzinfo=ZoneInfo("UTC"))

    save_runtime_state(tmp_path, state)
    loaded = load_runtime_state(tmp_path)

    assert "daily" in loaded.tasks
    assert loaded.tasks["daily"].status == "running"
    assert loaded.tasks["daily"].last_status == "success"
    assert loaded.tasks["daily"].last_run == task.last_run


def test_once_task_catch_up_and_complete():
    config = _config(
        """{
  "version": 1,
  "enabled": true,
  "timezone": "UTC",
  "tasks": [
    {
      "id": "wake",
      "kind": "once",
      "at": "2026-03-09T09:00:00+00:00",
      "session_key": "cli:123",
      "prompt": "Wake up reminder"
    }
  ]
}"""
    )
    state = ProactiveRuntimeState()
    now = datetime(2026, 3, 9, 10, 0, tzinfo=ZoneInfo("UTC"))

    due = evaluate_due_tasks(config, state, now=now, rng=Random(1))
    assert len(due) == 1
    assert due[0].task_id == "wake"

    mark_task_started(state, due[0], started_at=now)
    mark_task_finished(
        config.tasks[0],
        state,
        timezone_name=config.timezone,
        finished_at=now + timedelta(seconds=5),
        success=True,
        rng=Random(1),
    )

    later_due = evaluate_due_tasks(config, state, now=now + timedelta(hours=1), rng=Random(1))
    assert later_due == []
    assert state.tasks["wake"].completed_at is not None


def test_interval_restart_resumes_forward_without_replay():
    config = _config(
        """{
  "version": 1,
  "enabled": true,
  "timezone": "UTC",
  "tasks": [
    {
      "id": "heartbeat",
      "kind": "interval",
      "every_sec": 60,
      "session_key": "cli:123",
      "prompt": "Heartbeat"
    }
  ]
}"""
    )
    state = ProactiveRuntimeState()
    now = datetime(2026, 3, 9, 10, 0, tzinfo=ZoneInfo("UTC"))

    due = evaluate_due_tasks(config, state, now=now, rng=Random(1))
    assert due == []

    runtime = state.tasks["heartbeat"]
    assert runtime.next_run is not None
    assert runtime.next_run > now


def test_running_task_skips_overdue_tick_until_idle():
    config = _config(
        """{
  "version": 1,
  "enabled": true,
  "timezone": "UTC",
  "tasks": [
    {
      "id": "cron-task",
      "kind": "cron",
      "cron": "* * * * *",
      "session_key": "cli:123",
      "prompt": "Minute check"
    }
  ]
}"""
    )
    state = ProactiveRuntimeState()
    t0 = datetime(2026, 3, 9, 10, 5, tzinfo=ZoneInfo("UTC"))

    due = evaluate_due_tasks(config, state, now=t0, rng=Random(1))
    assert len(due) == 1
    mark_task_started(state, due[0], started_at=t0)

    # Still running 2 minutes later: scheduler should skip overdue tick(s), not emit due work.
    due_while_running = evaluate_due_tasks(config, state, now=t0 + timedelta(minutes=2), rng=Random(1))
    assert due_while_running == []
    assert state.tasks["cron-task"].next_run > t0 + timedelta(minutes=2)
