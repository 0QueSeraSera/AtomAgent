"""AtomAgent - Proactive, long-running AI agents."""

from atom_agent.agent import AgentLoop, ContextBuilder
from atom_agent.bus import InboundMessage, MessageBus, OutboundMessage
from atom_agent.env_config import Config, get_config
from atom_agent.memory import MemoryStore
from atom_agent.provider import LLMProvider, LLMResponse, ToolCallRequest
from atom_agent.session import Session, SessionManager
from atom_agent.tools import Tool, ToolRegistry

__all__ = [
    "AgentLoop",
    "ContextBuilder",
    "MessageBus",
    "InboundMessage",
    "OutboundMessage",
    "Config",
    "get_config",
    "LLMProvider",
    "LLMResponse",
    "ToolCallRequest",
    "Tool",
    "ToolRegistry",
    "Session",
    "SessionManager",
    "MemoryStore",
    # CLI
    "AsyncCLIChat",
    "run_interactive_chat",
]

__version__ = "0.1.0"


def __getattr__(name: str):
    """Lazy import for CLI module to avoid circular dependencies."""
    if name in ("AsyncCLIChat", "run_interactive_chat"):
        from atom_agent.cli import AsyncCLIChat, run_interactive_chat

        return AsyncCLIChat if name == "AsyncCLIChat" else run_interactive_chat
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
