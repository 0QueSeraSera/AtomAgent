"""Tests for FetchTool."""

import pytest

from atom_agent.tools.fetch import FetchTool


class TestFetchTool:
    """Test cases for FetchTool."""

    def test_name(self):
        """Test tool name."""
        tool = FetchTool()
        assert tool.name == "fetch"

    def test_description(self):
        """Test tool description."""
        tool = FetchTool()
        assert "HTTP" in tool.description

    def test_parameters_schema(self):
        """Test parameters schema."""
        tool = FetchTool()
        params = tool.parameters
        assert params["type"] == "object"
        assert "url" in params["properties"]
        assert "url" in params["required"]
        assert "method" in params["properties"]

    def test_validate_params_valid(self):
        """Test validation with valid params."""
        tool = FetchTool()
        errors = tool.validate_params({"url": "https://example.com"})
        assert errors == []

    def test_validate_params_missing_url(self):
        """Test validation with missing URL."""
        tool = FetchTool()
        errors = tool.validate_params({})
        assert len(errors) > 0
        assert "url" in errors[0].lower()

    def test_validate_params_invalid_method(self):
        """Test validation with invalid method."""
        tool = FetchTool()
        errors = tool.validate_params({"url": "https://example.com", "method": "INVALID"})
        assert len(errors) > 0

    @pytest.mark.asyncio
    async def test_execute_get_request(self):
        """Test GET request execution."""
        tool = FetchTool()
        # Using httpbin for testing
        result = await tool.execute(url="https://httpbin.org/get", method="GET")
        assert "Status: 200" in result
        assert "httpbin.org" in result

    @pytest.mark.asyncio
    async def test_execute_post_with_json(self):
        """Test POST request with JSON data."""
        tool = FetchTool()
        result = await tool.execute(
            url="https://httpbin.org/post",
            method="POST",
            json_data={"test": "data"},
        )
        assert "Status: 200" in result

    @pytest.mark.asyncio
    async def test_execute_timeout(self):
        """Test request timeout."""
        tool = FetchTool(default_timeout=0.001)
        result = await tool.execute(url="https://httpbin.org/delay/10", timeout=0.001)
        assert "Error" in result
        assert "timed out" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_invalid_url(self):
        """Test with invalid URL."""
        tool = FetchTool()
        result = await tool.execute(url="not-a-valid-url")
        assert "Error" in result

    def test_custom_timeout(self):
        """Test custom default timeout."""
        tool = FetchTool(default_timeout=60.0)
        assert tool._default_timeout == 60.0

    def test_max_response_size(self):
        """Test max response size configuration."""
        tool = FetchTool(max_response_size=1000)
        assert tool._max_response_size == 1000

    def test_to_schema(self):
        """Test OpenAI schema conversion."""
        tool = FetchTool()
        schema = tool.to_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "fetch"
        assert "parameters" in schema["function"]
