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


def preview_content(
    content: str, max_len: int = 500, head_len: int = 200, tail_len: int = 200
) -> str:
    """Create a head+tail preview for long content.

    Args:
        content: The content to preview
        max_len: Maximum total length before truncating
        head_len: Characters to show at the start
        tail_len: Characters to show at the end

    Returns:
        Preview string with head and tail, or full content if short enough
    """
    if len(content) <= max_len:
        return content
    truncated_count = len(content) - head_len - tail_len
    return (
        f"{content[:head_len]}\n... [{truncated_count} chars truncated] ...\n{content[-tail_len:]}"
    )


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
    # Redaction/utilities
    "truncate_content",
    "redact_api_key",
    "preview_content",
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
            messages: Full message list (preview logged at INFO, full at DEBUG with log_content=True)
            prompt_chars: Total character count of the prompt (optional, auto-calculated if not provided)
            **kwargs: Additional fields to log
        """
        extra: dict = {"model": model, "msg_count": msg_count, "tools": tools, **kwargs}

        # Calculate prompt character count
        if prompt_chars is not None:
            extra["prompt_chars"] = prompt_chars
        elif messages:
            total_chars = sum(
                len(str(m.get("content", ""))) if m.get("content") else 0 for m in messages
            )
            extra["prompt_chars"] = total_chars

        # Add message preview at INFO level
        if messages:
            extra["prompt_preview"] = self._preview_messages(messages)

        self.info("LLM request", extra=extra)  # type: ignore

        # Log full messages at DEBUG level if content logging is enabled
        if is_content_logging_enabled() and messages:
            self.debug("LLM request (full)", extra={"messages": messages, **kwargs})  # type: ignore

    def _preview_messages(self, messages: list, max_per_msg: int = 100) -> str:
        """Create a compact preview of the last few messages."""
        previews = []
        for m in messages[-3:]:  # Last 3 messages
            role = m.get("role", "?")
            content = str(m.get("content", "") or "")[:max_per_msg]
            previews.append(f"[{role}]: {content}")
        return " | ".join(previews)

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
            content: Full response content (preview logged at INFO, full at DEBUG with log_content=True)
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

        # Always log preview at INFO level
        if content:
            extra["content_preview"] = preview_content(content)
        self.info("LLM response", extra=extra)  # type: ignore

        # Also log full content at DEBUG level if content logging is enabled
        if is_content_logging_enabled() and content:
            self.debug("LLM response (full)", extra={"content": content, **kwargs})  # type: ignore

    def user_message(
        self,
        content: str,
        channel: str = "cli",
        chat_id: str = "unknown",
        **kwargs: object,
    ) -> None:
        """Log a user message received.

        Args:
            content: The user's message content
            channel: Communication channel (cli, api, etc.)
            chat_id: Chat/session identifier
            **kwargs: Additional fields to log
        """
        extra: dict = {
            "channel": channel,
            "chat_id": chat_id,
            "content_len": len(content),
            **kwargs,
        }

        # Always log preview at INFO level
        extra["content_preview"] = preview_content(content)
        self.info("User message", extra=extra)  # type: ignore

        # Also log full content at DEBUG level if content logging is enabled
        if is_content_logging_enabled():
            self.debug("User message (full)", extra={"content": content, **kwargs})  # type: ignore

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
            result: Tool result (preview logged at INFO, full at DEBUG with log_content=True)
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
            # Always log preview at INFO level
            extra["result_preview"] = preview_content(result)

        self.info("Tool call", extra=extra)  # type: ignore

        # Also log full result at DEBUG level if content logging is enabled
        if is_content_logging_enabled() and result:
            self.debug("Tool result (full)", extra={"tool_name": tool_name, "result": result})  # type: ignore


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
        log_dir = config.log_dir
        session_timestamp = generate_session_timestamp()

        handler: logging.Handler = MultiChannelHandler(
            base_path=log_dir,
            session_timestamp=session_timestamp,
            channels=config.channels_to_log,
            formatter=formatter,
        )
    elif config.output == "file":
        # Determine file path: use provided file_path or generate one
        if config.file_path:
            file_path = config.file_path
        else:
            config.log_dir.mkdir(parents=True, exist_ok=True)
            session_timestamp = generate_session_timestamp()
            file_path = config.log_dir / f"atom_agent_{session_timestamp}.log"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(file_path)
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
