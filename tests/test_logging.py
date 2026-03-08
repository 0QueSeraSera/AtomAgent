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
    MultiChannelHandler,
    StructuredFormatter,
    generate_session_timestamp,
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


class TestGenerateSessionTimestamp:
    """Tests for generate_session_timestamp function."""

    def test_format(self) -> None:
        """Should generate timestamp in YYYYMMDD_HHMMSS format."""
        timestamp = generate_session_timestamp()
        assert len(timestamp) == 15
        assert timestamp[8] == "_"
        # Check all characters are digits or underscore
        assert all(c.isdigit() or c == "_" for c in timestamp)

    def test_unique_per_call(self) -> None:
        """Should generate different timestamps (unless called very quickly)."""
        import time

        ts1 = generate_session_timestamp()
        time.sleep(1)  # Ensure different second
        ts2 = generate_session_timestamp()
        # At minimum, the seconds should be different
        assert ts1 != ts2


class TestMultiChannelHandler:
    """Tests for MultiChannelHandler."""

    def test_creates_main_log_file(self, tmp_path: Path) -> None:
        """Should create main combined log file."""
        handler = MultiChannelHandler(
            base_path=tmp_path,
            session_timestamp="20260308_142345",
            channels=["cli", "proactive"],
        )

        # Check main log file exists
        main_log = tmp_path / "atom_agent_20260308_142345.log"
        assert main_log.exists()

        handler.close()

    def test_routes_to_channel_files(self, tmp_path: Path) -> None:
        """Should route logs to appropriate channel files."""
        formatter = StructuredFormatter()
        handler = MultiChannelHandler(
            base_path=tmp_path,
            session_timestamp="20260308_142345",
            channels=["cli", "proactive"],
            formatter=formatter,
        )

        # Create a log record with channel=cli
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="CLI message",
            args=(),
            exc_info=None,
        )
        record.channel = "cli"  # type: ignore
        handler.emit(record)

        # Create a log record with channel=proactive
        record2 = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Proactive message",
            args=(),
            exc_info=None,
        )
        record2.channel = "proactive"  # type: ignore
        handler.emit(record2)

        handler.flush()
        handler.close()

        # Check main log has both messages
        main_log = tmp_path / "atom_agent_20260308_142345.log"
        main_content = main_log.read_text()
        assert "CLI message" in main_content
        assert "Proactive message" in main_content

        # Check cli log has only cli message
        cli_log = tmp_path / "atom_agent_20260308_142345_cli.log"
        cli_content = cli_log.read_text()
        assert "CLI message" in cli_content
        assert "Proactive message" not in cli_content

        # Check proactive log has only proactive message
        proactive_log = tmp_path / "atom_agent_20260308_142345_proactive.log"
        proactive_content = proactive_log.read_text()
        assert "Proactive message" in proactive_content
        assert "CLI message" not in proactive_content

    def test_no_channel_ignored(self, tmp_path: Path) -> None:
        """Records without channel should only go to main log."""
        handler = MultiChannelHandler(
            base_path=tmp_path,
            session_timestamp="20260308_142345",
            channels=["cli", "proactive"],
        )

        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="No channel message",
            args=(),
            exc_info=None,
        )
        # No channel attribute
        handler.emit(record)
        handler.close()

        # Main log should have message
        main_log = tmp_path / "atom_agent_20260308_142345.log"
        assert "No channel message" in main_log.read_text()

        # No channel-specific files should be created
        assert not (tmp_path / "atom_agent_20260308_142345_cli.log").exists()

    def test_filters_by_configured_channels(self, tmp_path: Path) -> None:
        """Should only create files for configured channels."""
        handler = MultiChannelHandler(
            base_path=tmp_path,
            session_timestamp="20260308_142345",
            channels=["cli"],  # Only cli configured
        )

        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="System message",
            args=(),
            exc_info=None,
        )
        record.channel = "system"  # type: ignore
        handler.emit(record)
        handler.close()

        # Main log should have message
        main_log = tmp_path / "atom_agent_20260308_142345.log"
        assert "System message" in main_log.read_text()

        # System log should NOT exist (not in configured channels)
        assert not (tmp_path / "atom_agent_20260308_142345_system.log").exists()

    def test_all_channels_when_none_specified(self, tmp_path: Path) -> None:
        """When channels is None, should log all encountered channels."""
        handler = MultiChannelHandler(
            base_path=tmp_path,
            session_timestamp="20260308_142345",
            channels=None,  # Log all channels
        )

        # Log to an arbitrary channel
        record = logging.LogRecord(
            name="test.module",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Custom message",
            args=(),
            exc_info=None,
        )
        record.channel = "custom_channel"  # type: ignore
        handler.emit(record)
        handler.close()

        # Custom channel file should be created
        custom_log = tmp_path / "atom_agent_20260308_142345_custom_channel.log"
        assert "Custom message" in custom_log.read_text()


class TestSeparateChannelsConfig:
    """Tests for separate_channels configuration."""

    def test_separate_channels_creates_files(self, tmp_path: Path, monkeypatch: Any) -> None:
        """separate_channels=True should create multiple log files."""
        import atom_agent.logging
        atom_agent.logging._CONFIGURED = False

        config = LoggingConfig(
            level="DEBUG",
            separate_channels=True,
            channels_to_log=["cli", "system"],
            log_dir=tmp_path,
        )
        setup_logging(config)

        logger = get_logger("test")
        logger.info("CLI message", extra={"channel": "cli"})
        logger.info("System message", extra={"channel": "system"})

        # Close handlers to flush
        for handler in logging.getLogger("atom_agent").handlers:
            handler.close()

        # Check files exist
        files = list(tmp_path.glob("atom_agent_*.log"))
        # Should have main + 2 channel files
        assert len(files) >= 3

        # Find main log (no channel suffix after timestamp)
        # Main log: atom_agent_TIMESTAMP.log (no trailing _channel)
        main_logs = [f for f in files if not any(
            f.name.endswith(f"_{ch}.log") for ch in ["cli", "system"]
        )]
        assert len(main_logs) >= 1
        main_content = main_logs[0].read_text()
        assert "CLI message" in main_content
        assert "System message" in main_content

    def test_env_var_override_separate_channels(self, monkeypatch: Any) -> None:
        """ATOM_AGENT_LOG_SEPARATE_CHANNELS should enable channel separation."""
        monkeypatch.setenv("ATOM_AGENT_LOG_SEPARATE_CHANNELS", "true")
        config = LoggingConfig()
        assert config.separate_channels is True

    def test_env_var_override_channels(self, monkeypatch: Any) -> None:
        """ATOM_AGENT_LOG_CHANNELS should set channels list."""
        monkeypatch.setenv("ATOM_AGENT_LOG_CHANNELS", "cli,proactive,system")
        config = LoggingConfig()
        assert config.channels_to_log == ["cli", "proactive", "system"]

    def test_env_var_override_log_dir(self, monkeypatch: Any) -> None:
        """ATOM_AGENT_LOG_DIR should set log directory."""
        monkeypatch.setenv("ATOM_AGENT_LOG_DIR", "/custom/logs")
        config = LoggingConfig()
        assert config.log_dir == Path("/custom/logs")
