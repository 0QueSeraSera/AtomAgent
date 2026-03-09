"""Unit tests for interactive CLI chat local commands."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from atom_agent.cli.chat import AsyncCLIChat
from atom_agent.provider.base import LLMProvider, LLMResponse


class DummyProvider(LLMProvider):
    """Minimal provider for CLI chat tests."""

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


class FakeSessions:
    """Simple session listing stub."""

    def __init__(self, keys: list[str]):
        self._keys = keys

    def list_sessions(self) -> list[dict[str, str]]:
        return [{"key": key, "updated_at": "2026-03-09T00:00:00"} for key in self._keys]


class FakeAgent:
    """Simple chat agent stub used by local command tests."""

    def __init__(self, keys: list[str]):
        self.sessions = FakeSessions(keys)

    async def switch_workspace(self, new_workspace: Path, workspace_name: str | None = None) -> bool:
        return True


def test_chat_starts_with_uuid_session_key(tmp_path: Path) -> None:
    """CLI chat should default to UUID session ids."""
    chat = AsyncCLIChat(provider=DummyProvider(), workspace=tmp_path)
    uuid.UUID(chat._current_chat_id)
    assert chat.current_session_key == f"cli:{chat._current_chat_id}"


@pytest.mark.asyncio
async def test_new_command_rotates_session_id(tmp_path: Path) -> None:
    """`/new` should rotate to a fresh UUID session id."""
    chat = AsyncCLIChat(provider=DummyProvider(), workspace=tmp_path)
    old_id = chat._current_chat_id
    handled = await chat._handle_local_command("/new")
    assert handled is True
    assert chat._current_chat_id != old_id
    uuid.UUID(chat._current_chat_id)


def test_resume_command_accepts_uuid_or_full_key(tmp_path: Path) -> None:
    """`/resume` should accept both raw UUID and full session key."""
    first = str(uuid.uuid4())
    second = str(uuid.uuid4())
    chat = AsyncCLIChat(provider=DummyProvider(), workspace=tmp_path)
    chat.agent = FakeAgent([f"cli:{first}", f"cli:{second}"])

    chat._resume_session(second)
    assert chat._current_chat_id == second

    chat._resume_session(f"cli:{first}")
    assert chat._current_chat_id == first
