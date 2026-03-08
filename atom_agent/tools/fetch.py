"""Fetch tool for making HTTP requests."""

import json
from typing import Any

import httpx

from atom_agent.logging import get_logger
from atom_agent.tools.base import Tool

logger = get_logger("tools.fetch")


class FetchTool(Tool):
    """Tool for making HTTP requests.

    Supports GET, POST, PUT, DELETE, PATCH methods with configurable
    headers, body, and timeout.
    """

    def __init__(
        self,
        default_timeout: float = 30.0,
        max_response_size: int = 100_000,
        follow_redirects: bool = True,
    ):
        self._default_timeout = default_timeout
        self._max_response_size = max_response_size
        self._follow_redirects = follow_redirects

    @property
    def name(self) -> str:
        return "fetch"

    @property
    def description(self) -> str:
        return (
            "Make HTTP requests to fetch data from URLs. "
            "Supports GET, POST, PUT, DELETE, PATCH methods. "
            "Returns response status, headers, and body."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to request",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "description": "HTTP method (default: GET)",
                },
                "headers": {
                    "type": "object",
                    "description": "HTTP headers as key-value pairs",
                },
                "body": {
                    "type": "string",
                    "description": "Request body (for POST, PUT, PATCH)",
                },
                "json_data": {
                    "type": "object",
                    "description": "JSON body as object (for POST, PUT, PATCH)",
                },
                "timeout": {
                    "type": "number",
                    "description": f"Timeout in seconds (default: {self._default_timeout})",
                },
            },
            "required": ["url"],
        }

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
        json_data: dict[str, Any] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> str:
        method = method.upper()
        timeout = timeout or self._default_timeout

        # Prepare request
        request_headers = headers or {}
        content = None
        json_content = None

        if body:
            content = body.encode("utf-8")
        elif json_data:
            json_content = json_data
            if "content-type" not in {k.lower() for k in request_headers}:
                request_headers["Content-Type"] = "application/json"

        logger.info(
            "Making HTTP request",
            extra={
                "method": method,
                "url": url,
                "has_body": body is not None or json_data is not None,
            },
        )

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=self._follow_redirects,
            ) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=request_headers,
                    content=content,
                    json=json_content,
                )

            # Truncate response if too large
            response_text = response.text
            truncated = False
            if len(response_text) > self._max_response_size:
                response_text = response_text[: self._max_response_size]
                truncated = True

            # Try to pretty-print JSON responses
            try:
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    parsed = json.loads(response_text)
                    response_text = json.dumps(parsed, indent=2)
            except (json.JSONDecodeError, TypeError):
                pass

            result_parts = [
                f"Status: {response.status_code}",
                f"URL: {str(response.url)}",
                f"Headers: {dict(response.headers)}",
            ]

            if truncated:
                result_parts.append(f"\n[Response truncated to {self._max_response_size} chars]")

            result_parts.append(f"\nBody:\n{response_text}")

            return "\n".join(result_parts)

        except httpx.TimeoutException:
            logger.warning("Request timed out", extra={"url": url, "timeout": timeout})
            return f"Error: Request timed out after {timeout} seconds"
        except httpx.RequestError as e:
            logger.error("Request failed", extra={"url": url, "error": str(e)})
            return f"Error: Request failed - {str(e)}"
        except Exception as e:
            logger.error("Unexpected error", extra={"url": url, "error": str(e)})
            return f"Error: {str(e)}"
