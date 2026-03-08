"""Tests for BashTool."""

import pytest

from atom_agent.tools.bash import BashTool


class TestBashTool:
    """Test cases for BashTool."""

    def test_name(self):
        """Test tool name."""
        tool = BashTool()
        assert tool.name == "bash"

    def test_description(self):
        """Test tool description."""
        tool = BashTool()
        assert "bash" in tool.description.lower() or "shell" in tool.description.lower()

    def test_parameters_schema(self):
        """Test parameters schema."""
        tool = BashTool()
        params = tool.parameters
        assert params["type"] == "object"
        assert "command" in params["properties"]
        assert "command" in params["required"]

    def test_validate_params_valid(self):
        """Test validation with valid params."""
        tool = BashTool()
        errors = tool.validate_params({"command": "echo hello"})
        assert errors == []

    def test_validate_params_missing_command(self):
        """Test validation with missing command."""
        tool = BashTool()
        errors = tool.validate_params({})
        assert len(errors) > 0
        assert "command" in errors[0].lower()

    @pytest.mark.asyncio
    async def test_execute_simple_command(self):
        """Test simple command execution."""
        tool = BashTool()
        result = await tool.execute(command="echo 'Hello, World!'")
        assert "Exit code: 0" in result
        assert "Hello, World!" in result

    @pytest.mark.asyncio
    async def test_execute_command_with_exit_code(self):
        """Test command that returns non-zero exit code."""
        tool = BashTool()
        result = await tool.execute(command="exit 1")
        assert "Exit code: 1" in result

    @pytest.mark.asyncio
    async def test_execute_command_with_stderr(self):
        """Test command that writes to stderr."""
        tool = BashTool()
        result = await tool.execute(command="echo 'error' >&2")
        assert "Exit code: 0" in result
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test command timeout."""
        tool = BashTool(default_timeout=0.1)
        result = await tool.execute(command="sleep 10", timeout=0.1)
        assert "Error" in result
        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_command_not_found(self):
        """Test with non-existent command."""
        tool = BashTool()
        result = await tool.execute(command="nonexistent_command_xyz123")
        assert "Exit code:" in result  # Returns non-zero exit code

    def test_blocked_commands(self):
        """Test blocked commands configuration."""
        tool = BashTool(blocked_commands=["rm", "sudo"])
        error = tool._validate_command("rm -rf /")
        assert error is not None
        assert "blocked" in error.lower()

        error = tool._validate_command("echo hello")
        assert error is None

    def test_allowed_commands(self):
        """Test allowed commands configuration."""
        tool = BashTool(allowed_commands=["echo", "ls"])
        error = tool._validate_command("echo hello")
        assert error is None

        error = tool._validate_command("rm file.txt")
        assert error is not None
        assert "not in allowed list" in error.lower()

    def test_custom_timeout(self):
        """Test custom default timeout."""
        tool = BashTool(default_timeout=120.0)
        assert tool._default_timeout == 120.0

    def test_max_output_size(self):
        """Test max output size configuration."""
        tool = BashTool(max_output_size=1000)
        assert tool._max_output_size == 1000

    @pytest.mark.asyncio
    async def test_execute_with_cwd(self):
        """Test command with custom working directory."""
        import tempfile

        tool = BashTool()
        with tempfile.TemporaryDirectory() as tmpdir:
            result = await tool.execute(command="pwd", cwd=tmpdir)
            assert "Exit code: 0" in result
            assert tmpdir in result

    @pytest.mark.asyncio
    async def test_execute_with_env(self):
        """Test command with custom environment variables."""
        tool = BashTool()
        result = await tool.execute(
            command="echo $TEST_VAR",
            env={"TEST_VAR": "custom_value"},
        )
        assert "Exit code: 0" in result
        assert "custom_value" in result

    def test_to_schema(self):
        """Test OpenAI schema conversion."""
        tool = BashTool()
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "bash"
        assert "parameters" in schema["function"]
