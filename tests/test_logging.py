"""Tests for the AtomAgent logging system."""

import json
import logging
import sys
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from atom_agent.logging import (
    JSONFormatter,
    LoggingConfig,
    StructuredFormatter,
    generate_trace_id,
    get_logger,
    get_session_key,
    get_trace_id,
    quick_setup,
    redact_api_key,
    set_session_key,
    set_trace_id,
    setup_logging,
    trace_context,
    truncate_content,
)


class TestTruncateContent:
    """Tests for truncate_content function."""

    def test_short_content_unchanged(self) -> None:
        """Short content should not be truncated."""
        text = "Hello, world!"
        assert truncate_content(text, max_len=200) == text

    def test_exact_length_unchanged(self) -> None:
        """Content at exact max length should not be truncated."""
        text = "a" * 100
        assert truncate_content(text, max_len=100) == text

    def test_long_content_truncated(self) -> None:
        """Long content should be truncated with ellipsis."""
        text = "a" * 300
        result = truncate_content(text, max_len=100)
        assert len(result) < 110  # Some room for ellipsis
        assert result.endswith("...")

    def test_word_boundary_truncation(self) -> None:
        """Should try to truncate at word boundary."""
        text = "hello world " + "a" * 200
        result = truncate_content(text, max_len=50)
        assert result.endswith("...")

    def test_none_returns_empty(self) -> None:
        """None should return empty string."""
        assert truncate_content(None) == ""

    def test_custom_max_len(self) -> None:
        """Should respect custom max_len."""
        text = "a" * 50
        result = truncate_content(text, max_len=20)
        assert len(result) < 25


class TestRedactApiKey:
    """Tests for redact_api_key function."""

    def test_redact_api_key_format(self) -> None:
        """Should redact api_key= prefixed values."""
        text = "Using api_key=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX for authentication"
        result = redact_api_key(text)
        assert "api_key=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" not in result
        assert "[REDACTED]" in result

    def test_redact_bearer_token(self) -> None:
        """Should redact Bearer tokens."""
        text = "Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456"
        result = redact_api_key(text)
        assert "Bearer abcdefghijklmnopqrstuvwxyz123456" not in result
        assert "[REDACTED]" in result

    def test_no_keys_unchanged(self) -> None:
        """Text without API keys should be unchanged."""
        text = "This is a normal message without any API keys."
        assert redact_api_key(text) == text

    def test_none_returns_empty(self) -> None:
        """None should return empty string."""
        assert redact_api_key(None) == ""

    def test_multiple_keys(self) -> None:
        """Should redact multiple API keys."""
        text = "Keys: Bearer XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX and api_key=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
        result = redact_api_key(text)
        assert "api_key=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" not in result
        assert "api_key=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" not in result
        assert result.count("[REDACTED]") == 2


class TestTraceContext:
    """Tests for trace context management."""

    def test_generate_trace_id(self) -> None:
        """Should generate 8-char hex trace ID."""
        trace_id = generate_trace_id()
        assert len(trace_id) == 8
        assert all(c in "0123456789abcdef" for c in trace_id)

    def test_unique_trace_ids(self) -> None:
        """Generated trace IDs should be unique."""
        ids = {generate_trace_id() for _ in range(100)}
        assert len(ids) > 90  # Allow some collisions, but should be rare

    def test_set_get_trace_id(self) -> None:
        """Should set and get trace ID."""
        set_trace_id("test123")
        assert get_trace_id() == "test123"
        set_trace_id(None)
        assert get_trace_id() is None

    def test_set_get_session_key(self) -> None:
        """Should set and get session key."""
        set_session_key("cli:demo")
        assert get_session_key() == "cli:demo"
        set_session_key(None)
        assert get_session_key() is None

    def test_trace_context_manager(self) -> None:
        """trace_context should set context temporarily."""
        # Initially no context
        set_trace_id(None)
        set_session_key(None)

        with trace_context(trace_id="abc123", session_key="cli:test"):
            assert get_trace_id() == "abc123"
            assert get_session_key() == "cli:test"

        # Should be restored after context
        assert get_trace_id() is None
        assert get_session_key() is None

    def test_trace_context_auto_generate(self) -> None:
        """trace_context should auto-generate trace_id if not provided."""
        with trace_context():
            trace_id = get_trace_id()
            assert trace_id is not None
            assert len(trace_id) == 8

    def test_trace_context_nested(self) -> None:
        """Nested trace_context should work correctly."""
        set_trace_id("outer")

        with trace_context(trace_id="inner1"):
            assert get_trace_id() == "inner1"
            with trace_context(trace_id="inner2"):
                assert get_trace_id() == "inner2"
            assert get_trace_id() == "inner1"

        assert get_trace_id() == "outer"


class TestStructuredFormatter:
    """Tests for StructuredFormatter."""

    def test_basic_format(self) -> None:
        """Should format basic log message."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        assert "[INFO" in result
        assert "[test.module]" in result
        assert "Test message" in result

    def test_format_with_extra_fields(self) -> None:
        """Should include extra fields in output."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.custom_field = "custom_value"  # type: ignore
        record.count = 42  # type: ignore

        result = formatter.format(record)
        assert "custom_field=custom_value" in result
        assert "count=42" in result

    def test_format_with_trace_context(self) -> None:
        """Should include trace context in output."""
        formatter = StructuredFormatter()

        with trace_context(trace_id="abc123", session_key="cli:demo"):
            record = logging.LogRecord(
                name="test.module",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            result = formatter.format(record)
            assert "[abc123]" in result
            assert "[cli:demo]" in result

    def test_redacts_api_keys(self) -> None:
        """Should redact API keys in output."""
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Using key Bearer XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        assert "api_key=XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX" not in result
        assert "[REDACTED]" in result

    def test_truncates_long_content(self) -> None:
        """Should truncate long content in extra fields."""
        formatter = StructuredFormatter(max_content_length=20)
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.long_content = "a" * 100  # type: ignore

        result = formatter.format(record)
        assert len(result) < 200  # Should be truncated


class TestJSONFormatter:
    """Tests for JSONFormatter."""

    def test_basic_json_format(self) -> None:
        """Should output valid JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["level"] == "INFO"
        assert data["component"] == "test.module"
        assert data["message"] == "Test message"
        assert "timestamp" in data

    def test_json_with_extra_fields(self) -> None:
        """Should include extra fields in JSON."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        record.model = "deepseek-chat"  # type: ignore
        record.tokens = 100  # type: ignore

        result = formatter.format(record)
        data = json.loads(result)

        assert data["model"] == "deepseek-chat"
        assert data["tokens"] == 100

    def test_json_with_trace_context(self) -> None:
        """Should include trace context in JSON."""
        formatter = JSONFormatter()

        with trace_context(trace_id="abc123", session_key="cli:demo"):
            record = logging.LogRecord(
                name="test.module",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test",
                args=(),
                exc_info=None,
            )
            result = formatter.format(record)
            data = json.loads(result)

            assert data["trace_id"] == "abc123"
            assert data["session_key"] == "cli:demo"

    def test_json_no_null_fields(self) -> None:
        """Should not include null fields in JSON."""
        formatter = JSONFormatter()

        # No trace context set
        set_trace_id(None)
        set_session_key(None)

        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Test",
            args=(),
            exc_info=None,
        )
        result = formatter.format(record)
        data = json.loads(result)

        assert "trace_id" not in data
        assert "session_key" not in data


class TestLoggingConfig:
    """Tests for LoggingConfig."""

    def test_default_config(self) -> None:
        """Should have sensible defaults."""
        config = LoggingConfig()
        assert config.level == "INFO"
        assert config.format == "text"
        assert config.output == "stderr"
        assert config.max_content_length == 200

    def test_custom_config(self) -> None:
        """Should accept custom values."""
        config = LoggingConfig(
            level="DEBUG",
            format="json",
            output="file",
            file_path=Path("/tmp/test.log"),
            max_content_length=500,
        )
        assert config.level == "DEBUG"
        assert config.format == "json"
        assert config.output == "file"
        assert config.file_path == Path("/tmp/test.log")

    def test_level_normalization(self) -> None:
        """Should normalize level to uppercase."""
        config = LoggingConfig(level="debug")
        assert config.level == "DEBUG"

    def test_invalid_level_defaults_to_info(self) -> None:
        """Invalid level should default to INFO."""
        config = LoggingConfig(level="INVALID")
        assert config.level == "INFO"


class TestSetupLogging:
    """Tests for setup_logging function."""

    def test_setup_creates_handler(self) -> None:
        """Should create handler on root logger."""
        # Reset configured state
        import atom_agent.logging
        atom_agent.logging._CONFIGURED = False

        setup_logging(LoggingConfig(level="DEBUG"))

        logger = logging.getLogger("atom_agent")
        assert len(logger.handlers) > 0
        assert logger.level == logging.DEBUG

    def test_quick_setup_debug(self, tmp_path: Path) -> None:
        """quick_setup debug mode should configure for development."""
        import atom_agent.logging
        atom_agent.logging._CONFIGURED = False

        quick_setup("debug")

        logger = logging.getLogger("atom_agent")
        assert logger.level == logging.DEBUG
        assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


class TestGetLogger:
    """Tests for get_logger function."""

    def test_prefixes_atom_agent(self) -> None:
        """Should prefix with atom_agent if not present."""
        logger = get_logger("test.module")
        assert logger.name == "atom_agent.test.module"

    def test_no_double_prefix(self) -> None:
        """Should not double prefix."""
        logger = get_logger("atom_agent.test.module")
        assert logger.name == "atom_agent.test.module"

    def test_returns_atom_agent_logger(self) -> None:
        """Should return AtomAgentLogger instance."""
        from atom_agent.logging import AtomAgentLogger

        logger = get_logger("test")
        assert isinstance(logger, AtomAgentLogger)


class TestAtomAgentLogger:
    """Tests for AtomAgentLogger convenience methods."""

    def test_llm_request_method(self, capsys: Any) -> None:
        """llm_request should log with correct fields."""
        import atom_agent.logging
        atom_agent.logging._CONFIGURED = False
        setup_logging(LoggingConfig(level="DEBUG"))

        logger = get_logger("test")
        logger.llm_request(model="test-model", msg_count=5, tools=3)

        # Just verify it doesn't raise
        captured = capsys.readouterr()
        assert "LLM request" in captured.err

    def test_llm_response_method(self, capsys: Any) -> None:
        """llm_response should log with correct fields."""
        import atom_agent.logging
        atom_agent.logging._CONFIGURED = False
        setup_logging(LoggingConfig(level="DEBUG"))

        logger = get_logger("test")
        logger.llm_response(content_len=100, tool_calls=2, tokens_in=50, tokens_out=25, duration_ms=123.4)

        captured = capsys.readouterr()
        assert "LLM response" in captured.err

    def test_tool_call_method(self, capsys: Any) -> None:
        """tool_call should log with correct fields."""
        import atom_agent.logging
        atom_agent.logging._CONFIGURED = False
        setup_logging(LoggingConfig(level="DEBUG"))

        logger = get_logger("test")
        logger.tool_call(tool_name="test_tool", params={"arg": "value"}, result="success", duration_ms=50.0)

        captured = capsys.readouterr()
        assert "Tool call" in captured.err
