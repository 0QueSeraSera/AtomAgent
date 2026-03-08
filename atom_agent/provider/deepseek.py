"""DeepSeek LLM provider using OpenAI-compatible API."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from atom_agent.provider.base import LLMProvider, LLMResponse, ToolCallRequest

logger = logging.getLogger(__name__)


class DeepSeekProvider(LLMProvider):
    """DeepSeek provider using OpenAI-compatible chat completions API."""

    API_BASE = "https://api.deepseek.com"

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        super().__init__(api_key=api_key)
        self.model = model
        self._client = httpx.AsyncClient(timeout=120.0)

    def get_default_model(self) -> str:
        return self.model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        """Send a chat completion request to DeepSeek."""
        model = model or self.model

        # Sanitize messages for OpenAI-compatible API
        allowed_keys = frozenset({"role", "content", "name", "tool_calls", "tool_call_id"})
        sanitized_messages = self._sanitize_request_messages(messages, allowed_keys)
        sanitized_messages = self._sanitize_empty_content(sanitized_messages)

        payload: dict[str, Any] = {
            "model": model,
            "messages": sanitized_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if tools:
            payload["tools"] = tools

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        logger.debug(f"DeepSeek request: model={model}, messages={len(messages)}, tools={len(tools) if tools else 0}")

        try:
            response = await self._client.post(
                f"{self.API_BASE}/chat/completions",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            content = message.get("content")
            finish_reason = choice.get("finish_reason", "stop")

            # Parse tool calls if present
            tool_calls = []
            raw_tool_calls = message.get("tool_calls", [])
            for tc in raw_tool_calls:
                function = tc.get("function", {})
                args = function.get("arguments", "{}")
                # Parse JSON arguments
                try:
                    parsed_args = json.loads(args) if isinstance(args, str) else args
                except json.JSONDecodeError:
                    parsed_args = {}

                tool_calls.append(ToolCallRequest(
                    id=tc.get("id", ""),
                    name=function.get("name", ""),
                    arguments=parsed_args,
                ))

            usage = data.get("usage", {})

            logger.debug(f"DeepSeek response: content_len={len(content) if content else 0}, tool_calls={len(tool_calls)}, finish_reason={finish_reason}")

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                usage=usage,
            )

        except httpx.HTTPStatusError as e:
            error_body = e.response.text if e.response else "Unknown error"
            logger.error(f"DeepSeek API error: {e.response.status_code} - {error_body}")
            return LLMResponse(
                content=None,
                finish_reason="error",
            )
        except Exception as e:
            logger.error(f"DeepSeek request failed: {e}")
            return LLMResponse(
                content=None,
                finish_reason="error",
            )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()
