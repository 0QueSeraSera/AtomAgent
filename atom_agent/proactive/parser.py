"""Parser for workspace-level PROACTIVE.md configuration."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from atom_agent.proactive.models import (
    ProactiveConfig,
    ProactiveTaskConfig,
    ProactiveTarget,
    ProactiveValidationError,
    ProactiveValidationIssue,
)

_JSON_FENCE_RE = re.compile(r"```json\s*(\{.*?\})\s*```", re.IGNORECASE | re.DOTALL)
_SESSION_KEY_RE = re.compile(r"^[^:\s]+:[^:\s]+$")
_CRON_FIELD_RE = re.compile(r"^[\d*/,\-]+$")
_SUPPORTED_VERSION = 1


def parse_proactive_file(path: Path) -> ProactiveConfig:
    """Load and parse a PROACTIVE.md file."""
    return parse_proactive_markdown(path.read_text(encoding="utf-8"), source_path=path)


def parse_proactive_markdown(markdown: str, source_path: Path | None = None) -> ProactiveConfig:
    """Parse markdown content and return normalized proactive config."""
    payload = _extract_json_payload(markdown)
    data = _decode_json(payload)
    return _validate_config(data, source_path=source_path)


def validate_proactive_markdown(
    markdown: str, source_path: Path | None = None
) -> list[ProactiveValidationIssue]:
    """Validate markdown content and return structured issues."""
    try:
        parse_proactive_markdown(markdown, source_path=source_path)
    except ProactiveValidationError as err:
        return err.issues
    return []


def _extract_json_payload(markdown: str) -> str:
    blocks = _JSON_FENCE_RE.findall(markdown)
    issues: list[ProactiveValidationIssue] = []
    if not blocks:
        issues.append(
            ProactiveValidationIssue(
                code="missing_json_block",
                path="PROACTIVE.md",
                message="Expected exactly one ```json ... ``` block.",
            )
        )
    elif len(blocks) > 1:
        issues.append(
            ProactiveValidationIssue(
                code="multiple_json_blocks",
                path="PROACTIVE.md",
                message="Found multiple JSON code blocks; keep exactly one.",
            )
        )

    if issues:
        raise ProactiveValidationError(issues)
    return blocks[0]


def _decode_json(payload: str) -> dict:
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ProactiveValidationError(
            [
                ProactiveValidationIssue(
                    code="invalid_json",
                    path=f"json:{exc.lineno}:{exc.colno}",
                    message=exc.msg,
                )
            ]
        ) from exc

    if not isinstance(decoded, dict):
        raise ProactiveValidationError(
            [
                ProactiveValidationIssue(
                    code="invalid_root_type",
                    path="json",
                    message="Top-level JSON must be an object.",
                )
            ]
        )
    return decoded


def _validate_config(data: dict, source_path: Path | None) -> ProactiveConfig:
    issues: list[ProactiveValidationIssue] = []

    version = data.get("version")
    if not isinstance(version, int):
        issues.append(_issue("invalid_type", "version", "Expected integer."))
    elif version != _SUPPORTED_VERSION:
        issues.append(
            _issue(
                "unsupported_version",
                "version",
                f"Unsupported version {version}; expected {_SUPPORTED_VERSION}.",
            )
        )

    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        issues.append(_issue("invalid_type", "enabled", "Expected boolean."))

    timezone = data.get("timezone", "UTC")
    if not isinstance(timezone, str) or not timezone.strip():
        issues.append(_issue("invalid_type", "timezone", "Expected non-empty string."))
    else:
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            issues.append(_issue("invalid_timezone", "timezone", f"Unknown timezone: {timezone}"))

    tasks_raw = data.get("tasks")
    if not isinstance(tasks_raw, list):
        issues.append(_issue("invalid_type", "tasks", "Expected array."))
        tasks_raw = []

    tasks: list[ProactiveTaskConfig] = []
    seen_ids: set[str] = set()
    for idx, raw_task in enumerate(tasks_raw):
        path = f"tasks[{idx}]"
        if not isinstance(raw_task, dict):
            issues.append(_issue("invalid_type", path, "Expected object."))
            continue

        task, task_issues = _validate_task(raw_task, path)
        if task_issues:
            issues.extend(task_issues)
            continue

        if task.task_id in seen_ids:
            issues.append(_issue("duplicate_id", f"{path}.id", f"Duplicate task id: {task.task_id}"))
            continue
        seen_ids.add(task.task_id)
        tasks.append(task)

    if issues:
        raise ProactiveValidationError(issues)

    return ProactiveConfig(
        version=version,
        enabled=enabled,
        timezone=timezone,
        tasks=tasks,
        source_path=source_path,
    )


def _validate_task(
    raw_task: dict,
    path: str,
) -> tuple[ProactiveTaskConfig | None, list[ProactiveValidationIssue]]:
    issues: list[ProactiveValidationIssue] = []

    task_id = raw_task.get("id")
    if not isinstance(task_id, str) or not task_id.strip():
        issues.append(_issue("invalid_type", f"{path}.id", "Expected non-empty string."))

    kind = raw_task.get("kind")
    if kind not in {"once", "cron", "interval"}:
        issues.append(
            _issue(
                "invalid_kind",
                f"{path}.kind",
                "Expected one of: once, cron, interval.",
            )
        )

    session_key = raw_task.get("session_key")
    if not isinstance(session_key, str) or not _SESSION_KEY_RE.match(session_key):
        issues.append(
            _issue(
                "invalid_session_key",
                f"{path}.session_key",
                "Expected `channel:chat_id` format.",
            )
        )

    prompt = raw_task.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        issues.append(_issue("invalid_type", f"{path}.prompt", "Expected non-empty string."))

    enabled = raw_task.get("enabled", True)
    if not isinstance(enabled, bool):
        issues.append(_issue("invalid_type", f"{path}.enabled", "Expected boolean."))

    jitter_sec = raw_task.get("jitter_sec", 0)
    if not isinstance(jitter_sec, int) or jitter_sec < 0:
        issues.append(_issue("invalid_type", f"{path}.jitter_sec", "Expected integer >= 0."))

    metadata = raw_task.get("metadata", {})
    if not isinstance(metadata, dict):
        issues.append(_issue("invalid_type", f"{path}.metadata", "Expected object."))

    target = _validate_target(raw_task.get("target"), path, issues)

    at = None
    cron_expr = None
    every_sec = None

    if kind == "once":
        at_raw = raw_task.get("at")
        if not isinstance(at_raw, str):
            issues.append(_issue("missing_field", f"{path}.at", "Required for once task."))
        else:
            try:
                at = datetime.fromisoformat(at_raw)
            except ValueError:
                issues.append(
                    _issue(
                        "invalid_datetime",
                        f"{path}.at",
                        "Expected ISO datetime string.",
                    )
                )
            else:
                if at.tzinfo is None:
                    issues.append(
                        _issue(
                            "missing_timezone",
                            f"{path}.at",
                            "Datetime must include timezone offset.",
                        )
                    )

    if kind == "cron":
        cron_expr = raw_task.get("cron")
        if not isinstance(cron_expr, str) or not cron_expr.strip():
            issues.append(_issue("missing_field", f"{path}.cron", "Required for cron task."))
        else:
            cron_fields = cron_expr.split()
            if len(cron_fields) != 5:
                issues.append(
                    _issue(
                        "invalid_cron",
                        f"{path}.cron",
                        "Cron expression must have 5 fields.",
                    )
                )
            elif not all(_CRON_FIELD_RE.match(field) for field in cron_fields):
                issues.append(
                    _issue(
                        "invalid_cron",
                        f"{path}.cron",
                        "Cron fields may only use digits and */,- characters.",
                    )
                )

    if kind == "interval":
        every_sec = raw_task.get("every_sec")
        if not isinstance(every_sec, int) or every_sec <= 0:
            issues.append(
                _issue(
                    "invalid_interval",
                    f"{path}.every_sec",
                    "Expected integer > 0 for interval task.",
                )
            )

    if issues:
        return None, issues

    return (
        ProactiveTaskConfig(
            task_id=task_id,
            kind=kind,
            session_key=session_key,
            prompt=prompt,
            target=target,
            enabled=enabled,
            jitter_sec=jitter_sec,
            metadata=metadata,
            at=at,
            cron=cron_expr,
            every_sec=every_sec,
        ),
        [],
    )


def _issue(code: str, path: str, message: str) -> ProactiveValidationIssue:
    return ProactiveValidationIssue(code=code, path=path, message=message)


def _validate_target(
    raw_target: object,
    task_path: str,
    issues: list[ProactiveValidationIssue],
) -> ProactiveTarget | None:
    if raw_target is None:
        return None

    path = f"{task_path}.target"
    if not isinstance(raw_target, dict):
        issues.append(_issue("invalid_type", path, "Expected object."))
        return None

    allowed_keys = {"channel", "chat_id", "reply_to", "thread_id"}
    unknown_keys = sorted(set(raw_target) - allowed_keys)
    if unknown_keys:
        issues.append(
            _issue(
                "unknown_field",
                path,
                f"Unknown field(s): {', '.join(unknown_keys)}.",
            )
        )

    channel = raw_target.get("channel")
    if not isinstance(channel, str) or not channel.strip():
        issues.append(_issue("invalid_type", f"{path}.channel", "Expected non-empty string."))

    chat_id = raw_target.get("chat_id")
    if not isinstance(chat_id, str) or not chat_id.strip():
        issues.append(_issue("invalid_type", f"{path}.chat_id", "Expected non-empty string."))

    reply_to = raw_target.get("reply_to")
    if reply_to is not None and (not isinstance(reply_to, str) or not reply_to.strip()):
        issues.append(_issue("invalid_type", f"{path}.reply_to", "Expected non-empty string."))

    thread_id = raw_target.get("thread_id")
    if thread_id is not None and (not isinstance(thread_id, str) or not thread_id.strip()):
        issues.append(_issue("invalid_type", f"{path}.thread_id", "Expected non-empty string."))

    if any(
        issue.path.startswith(path)
        for issue in issues
    ):
        return None

    return ProactiveTarget(
        channel=channel.strip(),
        chat_id=chat_id.strip(),
        reply_to=reply_to.strip() if isinstance(reply_to, str) else None,
        thread_id=thread_id.strip() if isinstance(thread_id, str) else None,
    )
