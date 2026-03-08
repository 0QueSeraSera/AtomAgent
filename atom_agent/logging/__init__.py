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
from atom_agent.logging.handlers import MultiChannelHandler, generate_session_timestamp
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
    # Content logging check
    "is_content_logging_enabled",
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
    # Handlers
    "MultiChannelHandler",
    "generate_session_timestamp",
    # Redaction utilities
    "truncate_content",
    "redact_api_key",
]

# Module-level flag to track if logging has been configured
_CONFIGURED = False
# Store config for access by logger methods
_CURRENT_CONFIG: LoggingConfig | None = None


def is_content_logging_enabled() -> bool:
    """Check if verbose content logging is enabled."""
    return _CURRENT_CONFIG is not None and _CURRENT_CONFIG.log_content


class AtomAgentLogger(logging.Logger):
    """Custom logger with convenience methods for AtomAgent."""

    def llm_request(
        self,
        model: str,
        msg_count: int,
        tools: int = 0,
        messages: list | None = None,
        prompt_chars: int | None = None,
        **kwargs: object,
    ) -> None:
        """Log an LLM request.

        Args:
            model: Model name
            msg_count: Number of messages
            tools: Number of tools available
            messages: Full message list (only logged if log_content=True)
            prompt_chars: Total character count of the prompt (optional, auto-calculated if not provided)
            **kwargs: Additional fields to log
        """
        extra: dict = {"model": model, "msg_count": msg_count, "tools": tools, **kwargs}

        # Calculate prompt character count
        if prompt_chars is not None:
            extra["prompt_chars"] = prompt_chars
        elif messages:
            total_chars = sum(
                len(str(m.get("content", ""))) if m.get("content") else 0
                for m in messages
            )
            extra["prompt_chars"] = total_chars

        # Log full messages if content logging is enabled
        if is_content_logging_enabled() and messages:
            extra["messages"] = messages  # type: ignore

        self.info("LLM request", extra=extra)  # type: ignore

    def llm_response(
        self,
        content_len: int,
        tool_calls: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        duration_ms: float = 0.0,
        content: str | None = None,
        **kwargs: object,
    ) -> None:
        """Log an LLM response.

        Args:
            content_len: Length of response content
            tool_calls: Number of tool calls in response
            tokens_in: Input tokens used
            tokens_out: Output tokens used
            duration_ms: Request duration in milliseconds
            content: Full response content (only logged if log_content=True)
            **kwargs: Additional fields to log
        """
        extra: dict = {
            "content_len": content_len,
            "tool_calls": tool_calls,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "duration_ms": round(duration_ms, 1),
            **kwargs,
        }

        # Log full content if content logging is enabled
        if is_content_logging_enabled() and content:
            extra["content"] = content  # type: ignore

        self.debug("LLM response", extra=extra)  # type: ignore

    def tool_call(
        self,
        tool_name: str,
        params: dict | None = None,
        result: str | None = None,
        duration_ms: float = 0.0,
        **kwargs: object,
    ) -> None:
        """Log a tool call.

        Args:
            tool_name: Name of the tool
            params: Tool parameters
            result: Tool result (full content only logged if log_content=True)
            duration_ms: Execution duration in milliseconds
            **kwargs: Additional fields to log
        """
        extra: dict = {
            "tool_name": tool_name,
            "duration_ms": round(duration_ms, 1),
            **kwargs,
        }
        if params:
            extra["params"] = params  # type: ignore
        if result:
            extra["result_len"] = len(result)  # type: ignore
            # Log full result if content logging is enabled
            if is_content_logging_enabled():
                extra["result"] = result  # type: ignore
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
    global _CONFIGURED, _CURRENT_CONFIG

    if config is None:
        config = LoggingConfig()

    # Store config for access by logger methods
    _CURRENT_CONFIG = config

    # Get root logger for atom_agent
    root_logger = logging.getLogger("atom_agent")

    # Set overall level
    level = getattr(logging, config.level, logging.INFO)
    root_logger.setLevel(level)

    # Remove existing handlers if reconfiguring
    if _CONFIGURED:
        root_logger.handlers.clear()

    # Create formatter based on format type
    if config.format == "json":
        formatter: logging.Formatter = JSONFormatter(max_content_length=config.max_content_length)
    else:
        formatter = StructuredFormatter(max_content_length=config.max_content_length)

    # Create handler based on configuration
    if config.separate_channels:
        # Use MultiChannelHandler for channel-based separation
        log_dir = config.log_dir or Path("./logs")
        session_timestamp = generate_session_timestamp()

        handler: logging.Handler = MultiChannelHandler(
            base_path=log_dir,
            session_timestamp=session_timestamp,
            channels=config.channels_to_log,
            formatter=formatter,
        )
    elif config.output == "file" and config.file_path:
        # Ensure directory exists
        config.file_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(config.file_path)
        handler.setFormatter(formatter)
    elif config.output == "stdout":
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)

    # Set handler level
    handler.setLevel(level)

    root_logger.addHandler(handler)

    # Set component-specific levels
    for component, comp_level in config.component_levels.items():
        comp_logger = logging.getLogger(f"atom_agent.{component}")
        comp_logger.setLevel(getattr(logging, comp_level.upper(), level))

    _CONFIGURED = True


def quick_setup(mode: Literal["debug", "production", "verbose"] = "debug") -> None:
    """
    Quick setup for common logging configurations.

    Args:
        mode: "debug" for verbose logging to stderr, "production" for JSON logging to file,
              "verbose" for full content logging (includes prompts, responses, tool results)
    """
    if mode == "debug":
        config = LoggingConfig(
            level="DEBUG",
            format="text",
            output="stderr",
            max_content_length=500,
        )
    elif mode == "verbose":
        config = LoggingConfig(
            level="DEBUG",
            format="json",
            output="file",
            file_path=Path("./logs/atom_agent_verbose.log"),
            max_content_length=10000,  # Allow long content
            log_content=True,  # Enable full content logging
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
