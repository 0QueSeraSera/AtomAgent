"""Custom log handlers for multi-channel file separation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path


class MultiChannelHandler(logging.Handler):
    """
    Handler that routes logs to multiple files based on channels.

    Creates:
    - A main combined log file with all records
    - Separate log files per configured channel

    File naming:
        main: atom_agent_{timestamp}.log
        channel: atom_agent_{timestamp}_{channel}.log

    Example:
        >>> handler = MultiChannelHandler(
        ...     base_path=Path("./logs"),
        ...     session_timestamp="20260308_142345",
        ...     channels=["cli", "proactive", "system"]
        ... )
    """

    def __init__(
        self,
        base_path: Path,
        session_timestamp: str,
        channels: list[str] | None = None,
        formatter: logging.Formatter | None = None,
    ) -> None:
        """
        Initialize the multi-channel handler.

        Args:
            base_path: Directory for log files
            session_timestamp: Session timestamp (YYYYMMDD_HHMMSS format)
            channels: List of channels to create separate files for.
                      If None, creates files for any channel encountered.
            formatter: Formatter to use for all handlers (defaults to StructuredFormatter)
        """
        super().__init__()

        self.base_path = base_path
        self.session_timestamp = session_timestamp
        self.configured_channels = set(channels) if channels else None

        # Ensure directory exists
        base_path.mkdir(parents=True, exist_ok=True)

        # Create formatters
        self.formatter = formatter

        # Create main combined handler
        self.main_handler = self._create_file_handler(
            base_path / f"atom_agent_{session_timestamp}.log"
        )

        # Channel-specific handlers (created lazily)
        self._channel_handlers: dict[str, logging.FileHandler] = {}

    def _create_file_handler(self, file_path: Path) -> logging.FileHandler:
        """Create a file handler with the configured formatter."""
        handler = logging.FileHandler(file_path)
        if self.formatter:
            handler.setFormatter(self.formatter)
        return handler

    def _get_channel_handler(self, channel: str) -> logging.FileHandler | None:
        """
        Get or create a handler for a specific channel.

        Returns None if the channel is not in the configured channels list
        (when specific channels are configured).
        """
        # Check if this channel should be logged
        if self.configured_channels is not None and channel not in self.configured_channels:
            return None

        # Create handler if not exists
        if channel not in self._channel_handlers:
            file_path = self.base_path / f"atom_agent_{self.session_timestamp}_{channel}.log"
            self._channel_handlers[channel] = self._create_file_handler(file_path)

        return self._channel_handlers[channel]

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record to appropriate files.

        Always emits to main combined log.
        Emits to channel-specific log if channel is present in record.
        """
        try:
            # Always emit to main log
            self.main_handler.emit(record)

            # Check for channel in extra
            channel = getattr(record, "channel", None)
            if channel:
                channel_handler = self._get_channel_handler(channel)
                if channel_handler:
                    channel_handler.emit(record)

        except Exception:
            self.handleError(record)

    def flush(self) -> None:
        """Flush all handlers."""
        self.main_handler.flush()
        for handler in self._channel_handlers.values():
            handler.flush()

    def close(self) -> None:
        """Close all handlers."""
        self.main_handler.close()
        for handler in self._channel_handlers.values():
            handler.close()
        super().close()

    def setFormatter(self, formatter: logging.Formatter) -> None:
        """Set formatter for all handlers."""
        self.formatter = formatter
        self.main_handler.setFormatter(formatter)
        for handler in self._channel_handlers.values():
            handler.setFormatter(formatter)


def generate_session_timestamp() -> str:
    """
    Generate a session timestamp for log file naming.

    Returns:
        Timestamp in YYYYMMDD_HHMMSS format
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%d_%H%M%S")
