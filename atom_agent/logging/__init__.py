"""
AtomAgent Logging System.

A comprehensive logging system for LLM observability, debugging, and AI readability.

Usage:
    from atom_agent.logging import setup_logging, get_logger, trace_context

    # Quick setup
    setup_logging()

    # Or with configuration
    from atom_agent.logging import LoggingConfig
    config = LoggingConfig(level="DEBUG", format="json")
    setup_logging(config)

    # Get a logger
    logger = get_logger("agent.loop")

    # Use with trace context
    with trace_context(session_key="cli:demo"):
        logger.info("Processing message", extra={"user_id": "user123"})
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from atom_agent.logging.config import LoggingConfig
from atom_agent.logging.context import (
    generate_trace_id,
    get_session_key,
    get_trace_id,
    set_session_key,
    set_trace_id,
    trace_context,
)
from atom_agent.logging.formatter import JSONFormatter, StructuredFormatter
from atom_agent.logging.redaction import redact_api_key, truncate_content

if TYPE_CHECKING:
    pass

__all__ = [
    # Configuration
    "LoggingConfig",
    # Setup functions
    "setup_logging",
    "quick_setup",
    "get_logger",
    # Context management
    "trace_context",
    "get_trace_id",
    "set_trace_id",
    "get_session_key",
    "set_session_key",
    "generate_trace_id",
    # Formatters
    "StructuredFormatter",
    "JSONFormatter",
    # Redaction utilities
    "truncate_content",
    "redact_api_key",
]

# Module-level flag to track if logging has been configured
_CONFIGURED = False


class AtomAgentLogger(logging.Logger):
    """Custom logger with convenience methods for AtomAgent."""

    def llm_request(
        self,
        model: str,
        msg_count: int,
        tools: int = 0,
        **kwargs: object,
    ) -> None:
        """Log an LLM request."""
        extra = {"model": model, "msg_count": msg_count, "tools": tools, **kwargs}
        self.info("LLM request", extra=extra)  # type: ignore

    def llm_response(
        self,
        content_len: int,
        tool_calls: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        duration_ms: float = 0.0,
        **kwargs: object,
    ) -> None:
        """Log an LLM response."""
        extra = {
            "content_len": content_len,
            "tool_calls": tool_calls,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "duration_ms": round(duration_ms, 1),
            **kwargs,
        }
        self.debug("LLM response", extra=extra)  # type: ignore

    def tool_call(
        self,
        tool_name: str,
        params: dict | None = None,
        result: str | None = None,
        duration_ms: float = 0.0,
        **kwargs: object,
    ) -> None:
        """Log a tool call."""
        extra = {
            "tool_name": tool_name,
            "duration_ms": round(duration_ms, 1),
            **kwargs,
        }
        if params:
            extra["params"] = params  # type: ignore
        if result:
            extra["result_len"] = len(result)  # type: ignore
        self.debug("Tool call", extra=extra)  # type: ignore


def get_logger(name: str) -> AtomAgentLogger:
    """
    Get a logger for the given component.

    Args:
        name: Logger name (typically module path like "agent.loop")

    Returns:
        Configured logger instance
    """
    # Prefix with atom_agent if not already
    if not name.startswith("atom_agent"):
        name = f"atom_agent.{name}"

    logging.setLoggerClass(AtomAgentLogger)
    return logging.getLogger(name)  # type: ignore


def setup_logging(config: LoggingConfig | None = None) -> None:
    """
    Set up logging for AtomAgent.

    Args:
        config: Optional logging configuration. If not provided, uses defaults
                and environment variables.
    """
    global _CONFIGURED

    if config is None:
        config = LoggingConfig()

    # Get root logger for atom_agent
    root_logger = logging.getLogger("atom_agent")

    # Set overall level
    level = getattr(logging, config.level, logging.INFO)
    root_logger.setLevel(level)

    # Remove existing handlers if reconfiguring
    if _CONFIGURED:
        root_logger.handlers.clear()

    # Create handler based on output type
    if config.output == "file" and config.file_path:
        # Ensure directory exists
        config.file_path.parent.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.FileHandler(config.file_path)
    elif config.output == "stdout":
        handler = logging.StreamHandler(sys.stdout)
    else:
        handler = logging.StreamHandler(sys.stderr)

    # Set handler level
    handler.setLevel(level)

    # Create formatter based on format type
    if config.format == "json":
        formatter: logging.Formatter = JSONFormatter(max_content_length=config.max_content_length)
    else:
        formatter = StructuredFormatter(max_content_length=config.max_content_length)

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Set component-specific levels
    for component, comp_level in config.component_levels.items():
        comp_logger = logging.getLogger(f"atom_agent.{component}")
        comp_logger.setLevel(getattr(logging, comp_level.upper(), level))

    _CONFIGURED = True


def quick_setup(mode: Literal["debug", "production"] = "debug") -> None:
    """
    Quick setup for common logging configurations.

    Args:
        mode: "debug" for verbose logging to stderr, "production" for JSON logging to file
    """
    if mode == "debug":
        config = LoggingConfig(
            level="DEBUG",
            format="text",
            output="stderr",
            max_content_length=500,
        )
    else:  # production
        config = LoggingConfig(
            level="INFO",
            format="json",
            output="file",
            file_path=Path("./logs/atom_agent.log"),
            max_content_length=200,
        )

    setup_logging(config)
