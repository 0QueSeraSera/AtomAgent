"""Async-safe context for request tracing."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Generator

# Context variables for async-safe request tracing
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_session_key: ContextVar[str | None] = ContextVar("session_key", default=None)


def generate_trace_id() -> str:
    """Generate a unique trace ID (8-char hex)."""
    return uuid.uuid4().hex[:8]


def get_trace_id() -> str | None:
    """Get the current trace ID."""
    return _trace_id.get()


def set_trace_id(trace_id: str | None) -> None:
    """Set the trace ID for the current context."""
    _trace_id.set(trace_id)


def get_session_key() -> str | None:
    """Get the current session key."""
    return _session_key.get()


def set_session_key(session_key: str | None) -> None:
    """Set the session key for the current context."""
    _session_key.set(session_key)


@contextmanager
def trace_context(
    trace_id: str | None = None,
    session_key: str | None = None,
) -> Generator[None, None, None]:
    """
    Context manager for setting trace context.

    Usage:
        with trace_context(trace_id="abc123", session_key="cli:demo"):
            logger.info("Processing message")

    Args:
        trace_id: Optional trace ID (auto-generated if not provided)
        session_key: Optional session key

    Yields:
        None
    """
    # Generate trace ID if not provided
    actual_trace_id = trace_id or generate_trace_id()

    # Save old values
    old_trace_id = _trace_id.get()
    old_session_key = _session_key.get()

    # Set new values
    _trace_id.set(actual_trace_id)
    if session_key is not None:
        _session_key.set(session_key)

    try:
        yield
    finally:
        # Restore old values
        _trace_id.set(old_trace_id)
        _session_key.set(old_session_key)
