"""LLM provider interface."""

from atom_agent.provider.base import LLMProvider, LLMResponse, ToolCallRequest
from atom_agent.provider.deepseek import DeepSeekProvider

__all__ = ["LLMProvider", "LLMResponse", "ToolCallRequest", "DeepSeekProvider"]

# Re-export logging utilities for provider implementations
from atom_agent.logging import get_logger as _get_logger


def get_provider_logger(name: str):
    """Get a logger for a provider implementation."""
    return _get_logger(f"provider.{name}")
