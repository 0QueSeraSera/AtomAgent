"""Tests for default model-facing tool registration."""

from __future__ import annotations

from pathlib import Path

import pytest

from atom_agent import AgentLoop, MessageBus
from atom_agent.agent.context import ContextBuilder
from atom_agent.provider.base import LLMProvider, LLMResponse
from atom_agent.tools.message import MessageTool
from atom_agent.workspace import WorkspaceManager


class DummyProvider(LLMProvider):
    """Minimal provider for tool-registration tests."""

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        reasoning_effort: str | None = None,
    ) -> LLMResponse:
        return LLMResponse(content="ok")

    def get_default_model(self) -> str:
        return "dummy-model"


def test_agent_loop_registers_fetch_and_bash_by_default(tmp_path: Path) -> None:
    """Default model-facing tools should include bash/fetch + memory retrieval."""
    agent = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
    )

    assert agent.tools.tool_names == ["fetch", "memory_search", "memory_read", "bash"]
    names = {item["function"]["name"] for item in agent.tools.get_definitions()}
    assert names == {"fetch", "bash", "memory_search", "memory_read"}
    assert "message" not in names


def test_context_prompt_does_not_instruct_message_tool(tmp_path: Path) -> None:
    """System prompt should not instruct the model to call `message`."""
    workspace = tmp_path / "ctx"
    WorkspaceManager(workspace).init_workspace(name="ctx")

    prompt = ContextBuilder(workspace).build_system_prompt()
    assert "message tool" not in prompt.lower()
    assert "Use the 'message' tool" not in prompt


def test_register_message_tool_is_rejected(tmp_path: Path) -> None:
    """Message transport should stay runtime-only, not model-callable."""
    agent = AgentLoop(
        bus=MessageBus(),
        provider=DummyProvider(),
        workspace=tmp_path,
    )

    with pytest.raises(ValueError, match="not model-facing"):
        agent.register_tool(MessageTool())
