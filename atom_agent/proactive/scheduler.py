"""Scheduling logic for proactive task execution."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from atom_agent.proactive.models import (
    DueTask,
    ProactiveConfig,
    ProactiveRuntimeState,
    ProactiveTaskConfig,
)

_MAX_CRON_SCAN_MINUTES = 366 * 24 * 60


def evaluate_due_tasks(
    config: ProactiveConfig,
    runtime_state: ProactiveRuntimeState,
    *,
    now: datetime | None = None,
    rng: random.Random | None = None,
) -> list[DueTask]:
    """Compute due tasks and update runtime_state in-place for scheduling metadata."""
    if not config.enabled:
        return []

    timezone = ZoneInfo(config.timezone)
    now = _ensure_aware(now or datetime.now(timezone), timezone)
    due_tasks: list[DueTask] = []

    for task in config.tasks:
        if not task.enabled:
            continue

        runtime = runtime_state.get_or_create_task(task.task_id)
        if task.kind == "once" and runtime.completed_at:
            continue

        if runtime.next_run is None:
            _initialize_next_run(task, runtime, now, timezone, rng)

        if runtime.next_run is None:
            continue

        if runtime.next_run <= now:
            if runtime.status == "running":
                _skip_overdue_ticks(task, runtime, now, timezone, rng)
                continue

            due_tasks.append(
                DueTask(
                    task_id=task.task_id,
                    kind=task.kind,
                    session_key=task.session_key,
                    prompt=task.prompt,
                    target=task.target,
                    scheduled_time=runtime.next_run,
                    base_time=runtime.next_base_run or runtime.next_run,
                )
            )

    return due_tasks


def mark_task_started(
    runtime_state: ProactiveRuntimeState,
    due_task: DueTask,
    *,
    started_at: datetime,
) -> None:
    """Mark a due task as running."""
    runtime = runtime_state.get_or_create_task(due_task.task_id)
    runtime.status = "running"
    runtime.last_run = started_at
    runtime.last_scheduled_run = due_task.scheduled_time
    runtime.last_scheduled_base = due_task.base_time


def mark_task_finished(
    task: ProactiveTaskConfig,
    runtime_state: ProactiveRuntimeState,
    *,
    timezone_name: str,
    finished_at: datetime,
    success: bool,
    error: str | None = None,
    rng: random.Random | None = None,
) -> None:
    """Mark task completion and schedule the next occurrence."""
    timezone = ZoneInfo(timezone_name)
    runtime = runtime_state.get_or_create_task(task.task_id)
    runtime.status = "idle"
    runtime.last_status = "success" if success else "failed"
    runtime.last_error = None if success else (error or "unknown error")

    if task.kind == "once":
        if success:
            runtime.completed_at = finished_at
            runtime.next_run = None
            runtime.next_base_run = None
        else:
            runtime.next_base_run = finished_at
            runtime.next_run = finished_at
        return

    if task.kind == "cron":
        anchor = runtime.last_scheduled_base or _ensure_aware(finished_at, timezone)
        next_base = _next_cron_occurrence(task.cron or "* * * * *", timezone, anchor, inclusive=False)
        runtime.next_base_run = next_base
        runtime.next_run = next_base + timedelta(seconds=_sample_delay(task.jitter_sec, rng))
        return

    anchor = runtime.last_scheduled_run or _ensure_aware(finished_at, timezone)
    next_base = anchor + timedelta(seconds=task.every_sec or 0)
    runtime.next_base_run = next_base
    runtime.next_run = next_base + timedelta(seconds=_sample_delay(task.jitter_sec, rng))


def _initialize_next_run(
    task: ProactiveTaskConfig,
    runtime,
    now: datetime,
    timezone: ZoneInfo,
    rng: random.Random | None,
) -> None:
    if task.kind == "once":
        if task.at is None:
            return
        base = _ensure_aware(task.at, timezone)
        runtime.next_base_run = base
        runtime.next_run = base + timedelta(seconds=_sample_delay(task.jitter_sec, rng))
        return

    if task.kind == "cron":
        base = _latest_cron_occurrence(task.cron or "* * * * *", timezone, now)
        if base is None:
            base = _next_cron_occurrence(task.cron or "* * * * *", timezone, now, inclusive=True)
        runtime.next_base_run = base
        runtime.next_run = base + timedelta(seconds=_sample_delay(task.jitter_sec, rng))
        return

    next_base = now + timedelta(seconds=task.every_sec or 0)
    runtime.next_base_run = next_base
    runtime.next_run = next_base + timedelta(seconds=_sample_delay(task.jitter_sec, rng))


def _skip_overdue_ticks(
    task: ProactiveTaskConfig,
    runtime,
    now: datetime,
    timezone: ZoneInfo,
    rng: random.Random | None,
) -> None:
    if task.kind == "once":
        return

    if task.kind == "cron":
        base = runtime.next_base_run or _ensure_aware(now, timezone)
        while runtime.next_run and runtime.next_run <= now:
            base = _next_cron_occurrence(task.cron or "* * * * *", timezone, base, inclusive=False)
            runtime.next_base_run = base
            runtime.next_run = base + timedelta(seconds=_sample_delay(task.jitter_sec, rng))
        return

    while runtime.next_run and runtime.next_run <= now:
        base = runtime.next_run + timedelta(seconds=task.every_sec or 0)
        runtime.next_base_run = base
        runtime.next_run = base + timedelta(seconds=_sample_delay(task.jitter_sec, rng))


def _sample_delay(jitter_sec: int, rng: random.Random | None) -> int:
    if jitter_sec <= 0:
        return 0
    rand = rng if rng is not None else random
    return rand.randint(0, jitter_sec)


def _ensure_aware(value: datetime, timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


@lru_cache(maxsize=128)
def _parse_cron(expr: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError("Cron expression must have exactly 5 fields.")

    minute = _parse_cron_field(fields[0], 0, 59)
    hour = _parse_cron_field(fields[1], 0, 23)
    day = _parse_cron_field(fields[2], 1, 31)
    month = _parse_cron_field(fields[3], 1, 12)
    dow = _parse_cron_field(fields[4], 0, 6)
    return minute, hour, day, month, dow


def _parse_cron_field(field: str, min_value: int, max_value: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise ValueError("Empty cron field segment.")

        if "/" in part:
            base_part, step_part = part.split("/", 1)
            step = int(step_part)
            if step <= 0:
                raise ValueError("Cron step must be > 0.")
        else:
            base_part = part
            step = 1

        if base_part == "*":
            start, end = min_value, max_value
        elif "-" in base_part:
            start_text, end_text = base_part.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError("Cron range start must be <= end.")
        else:
            single = int(base_part)
            start, end = single, single

        if start < min_value or end > max_value:
            raise ValueError("Cron value out of allowed range.")

        for value in range(start, end + 1, step):
            values.add(value)

    if not values:
        raise ValueError("Cron field resolved to empty value set.")
    return values


def _cron_matches(expr: str, value: datetime) -> bool:
    minute, hour, day, month, dow = _parse_cron(expr)
    cron_dow = (value.weekday() + 1) % 7
    return (
        value.minute in minute
        and value.hour in hour
        and value.day in day
        and value.month in month
        and cron_dow in dow
    )


def _next_cron_occurrence(
    expr: str,
    timezone: ZoneInfo,
    after: datetime,
    *,
    inclusive: bool,
) -> datetime:
    cursor = _ensure_aware(after, timezone).replace(second=0, microsecond=0)
    if inclusive:
        if after.second or after.microsecond:
            cursor += timedelta(minutes=1)
    else:
        cursor += timedelta(minutes=1)

    for _ in range(_MAX_CRON_SCAN_MINUTES):
        if _cron_matches(expr, cursor):
            return cursor
        cursor += timedelta(minutes=1)
    raise ValueError(f"Unable to find next cron occurrence for expression: {expr}")


def _latest_cron_occurrence(expr: str, timezone: ZoneInfo, now: datetime) -> datetime | None:
    cursor = _ensure_aware(now, timezone).replace(second=0, microsecond=0)
    for _ in range(_MAX_CRON_SCAN_MINUTES):
        if _cron_matches(expr, cursor) and cursor <= now.astimezone(timezone):
            return cursor
        cursor -= timedelta(minutes=1)
    return None
