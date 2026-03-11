"""Tests for AgentLoop MCP lifecycle integration."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from atom_agent import AgentLoop, MessageBus
from atom_agent.provider.base import LLMProvider, LLMResponse
from atom_agent.workspace import WorkspaceManager


class DummyProvider(LLMProvider):
    """Minimal provider for lifecycle tests."""

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


class FakeMCPManager:
    """Simple MCP manager stub for lifecycle assertions."""

    def __init__(
        self,
        *,
        connected_servers: list[str] | None = None,
        registered_tool_names: list[str] | None = None,
    ):
        self.connected_servers = connected_servers or []
        self.registered_tool_names = registered_tool_names or []
        self.connect_calls = 0
        self.close_calls = 0

    async def connect_from_workspace(self) -> list[str]:
        self.connect_calls += 1
        return list(self.registered_tool_names)

    async def close(self) -> None:
        self.close_calls += 1


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise TimeoutError("Condition not met before timeout")


@pytest.mark.asyncio
async def test_agent_run_connects_and_closes_mcp(tmp_path: Path) -> None:
    workspace = tmp_path / "run-mcp"
    WorkspaceManager(workspace).init_workspace(name="run-mcp")
    agent = AgentLoop(bus=MessageBus(), provider=DummyProvider(), workspace=workspace)

    fake = FakeMCPManager(connected_servers=["graph"], registered_tool_names=["mcp_graph_query"])
    agent._mcp = fake  # type: ignore[assignment]

    task = asyncio.create_task(agent.run())
    await _wait_for(lambda: fake.connect_calls == 1)
    agent.stop()
    await asyncio.wait_for(task, timeout=3.0)

    assert fake.close_calls >= 1


@pytest.mark.asyncio
async def test_switch_workspace_reloads_mcp_manager(tmp_path: Path) -> None:
    ws1 = tmp_path / "ws-1"
    ws2 = tmp_path / "ws-2"
    WorkspaceManager(ws1).init_workspace(name="ws-1")
    WorkspaceManager(ws2).init_workspace(name="ws-2")
    agent = AgentLoop(bus=MessageBus(), provider=DummyProvider(), workspace=ws1)

    old_manager = FakeMCPManager(connected_servers=["old"], registered_tool_names=["mcp_old_tool"])
    new_manager = FakeMCPManager(connected_servers=["new"], registered_tool_names=["mcp_new_tool"])
    agent._mcp = old_manager  # type: ignore[assignment]
    agent._create_mcp_manager = lambda workspace: new_manager  # type: ignore[method-assign]

    switched = await agent.switch_workspace(ws2, "ws-2")
    assert switched is True
    assert old_manager.close_calls == 1
    assert new_manager.connect_calls == 1
    assert agent.workspace == ws2
    assert agent.workspace_name == "ws-2"


def test_get_workspace_info_reports_skills_and_mcp(tmp_path: Path) -> None:
    workspace = tmp_path / "info-mcp"
    WorkspaceManager(workspace).init_workspace(name="info-mcp")
    (workspace / "skills" / "enabled-skill").mkdir(parents=True)
    (workspace / "skills" / "enabled-skill" / "SKILL.md").write_text("# Enabled\n", encoding="utf-8")
    (workspace / "skills" / "disabled-skill").mkdir(parents=True)
    (workspace / "skills" / "disabled-skill" / "SKILL.md").write_text(
        "# Disabled\n", encoding="utf-8"
    )
    (workspace / "skills" / "manifest.json").write_text(
        json.dumps(
            {
                "version": 1,
                "skills": {"disabled-skill": {"enabled": False}},
            }
        ),
        encoding="utf-8",
    )

    agent = AgentLoop(bus=MessageBus(), provider=DummyProvider(), workspace=workspace)
    agent._mcp = FakeMCPManager(  # type: ignore[assignment]
        connected_servers=["repo_graph"], registered_tool_names=["mcp_repo_graph_query"]
    )

    info = agent.get_workspace_info()
    assert info["skills"]["installed"] == 2
    assert info["skills"]["enabled"] == 1
    assert info["mcp"]["servers"] == ["repo_graph"]
    assert info["mcp"]["tools"] == ["mcp_repo_graph_query"]
