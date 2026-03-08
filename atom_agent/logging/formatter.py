"""Custom log formatters for structured logging."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from atom_agent.logging.context import get_session_key, get_trace_id
from atom_agent.logging.redaction import redact_api_key, truncate_content


class StructuredFormatter(logging.Formatter):
    """
    Human-readable structured formatter with key=value pairs.

    Format:
        [TIMESTAMP] [LEVEL] [COMPONENT] [trace_id] [session_key] message | key=value key2=value2

    Example:
        [2024-03-08 14:23:45.123] [INFO] [agent.loop] [abc123] [cli:demo] LLM request | model=deepseek-chat iteration=1
    """

    def __init__(
        self,
        max_content_length: int = 200,
        redact_keys: bool = True,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.max_content_length = max_content_length
        self.redact_keys = redact_keys

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record."""
        # Get timestamp
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}"

        # Get level (pad to 5 chars)
        level = record.levelname.ljust(5)

        # Get component (module name with parent)
        component = record.name

        # Get trace context
        trace_id = get_trace_id() or "-"
        session_key = get_session_key() or "-"

        # Get message and redact if needed
        message = record.getMessage()
        if self.redact_keys:
            message = redact_api_key(message)

        # Build base message
        parts = [
            f"[{timestamp}]",
            f"[{level}]",
            f"[{component}]",
            f"[{trace_id}]",
            f"[{session_key}]",
        ]

        # Add message
        parts.append(message)

        # Add extra fields if present
        extra_fields = self._get_extra_fields(record)
        if extra_fields:
            parts.append("|")
            parts.extend(extra_fields)

        result = " ".join(parts)

        # Add exception info if present
        if record.exc_info:
            result += "\n" + self.formatException(record.exc_info)

        return result

    def _get_extra_fields(self, record: logging.LogRecord) -> list[str]:
        """Extract extra fields from the log record."""
        # Standard attributes to skip
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "message",
            "asctime",
        }

        fields = []
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in standard_attrs:
                continue

            # Format value
            formatted_value = self._format_value(value)
            fields.append(f"{key}={formatted_value}")

        return fields

    def _format_value(self, value: Any) -> str:
        """Format a value for logging."""
        if isinstance(value, str):
            # Truncate long strings
            truncated = truncate_content(value, self.max_content_length)
            if self.redact_keys:
                truncated = redact_api_key(truncated)
            # Quote if contains spaces
            if " " in truncated or not truncated:
                return f'"{truncated}"'
            return truncated
        elif isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, (int, float)):
            return str(value)
        elif value is None:
            return "null"
        else:
            # For complex types, use repr and truncate
            text = truncate_content(repr(value), self.max_content_length)
            if self.redact_keys:
                text = redact_api_key(text)
            return f'"{text}"'


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for machine-parsable logs.

    Example:
        {"timestamp":"2024-03-08T14:23:45.123Z","level":"INFO","component":"agent.loop","trace_id":"abc123","session_key":"cli:demo","message":"LLM request","model":"deepseek-chat"}
    """

    def __init__(
        self,
        max_content_length: int = 500,
        redact_keys: bool = True,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.max_content_length = max_content_length
        self.redact_keys = redact_keys

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record as JSON."""
        # Get timestamp in ISO format
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond:06d}" + "Z"

        # Build log entry
        entry: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "component": record.name,
            "trace_id": get_trace_id(),
            "session_key": get_session_key(),
            "message": record.getMessage(),
        }

        # Redact if needed
        if self.redact_keys:
            entry["message"] = redact_api_key(entry["message"])

        # Add extra fields
        extra_fields = self._get_extra_fields(record)
        entry.update(extra_fields)

        # Add exception info if present
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        # Remove None values
        entry = {k: v for k, v in entry.items() if v is not None}

        return json.dumps(entry, ensure_ascii=False)

    def _get_extra_fields(self, record: logging.LogRecord) -> dict[str, Any]:
        """Extract extra fields from the log record."""
        standard_attrs = {
            "name",
            "msg",
            "args",
            "created",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "exc_info",
            "exc_text",
            "thread",
            "threadName",
            "message",
            "asctime",
        }

        fields: dict[str, Any] = {}
        for key, value in record.__dict__.items():
            if key.startswith("_") or key in standard_attrs:
                continue

            fields[key] = self._format_value(value)

        return fields

    def _format_value(self, value: Any) -> Any:
        """Format a value for JSON logging."""
        if isinstance(value, str):
            truncated = truncate_content(value, self.max_content_length)
            if self.redact_keys:
                truncated = redact_api_key(truncated)
            return truncated
        elif isinstance(value, (bool, int, float, type(None))):
            return value
        elif isinstance(value, (list, dict)):
            return value
        else:
            text = truncate_content(repr(value), self.max_content_length)
            if self.redact_keys:
                text = redact_api_key(text)
            return text
