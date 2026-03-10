"""Per-workspace daemon runtime for proactive task dispatch."""

from __future__ import annotations

from pathlib import Path

from atom_agent.agent import AgentLoop
from atom_agent.bus import MessageBus, OutboundMessage
from atom_agent.proactive import DueTask
from atom_agent.provider.base import LLMProvider


def parse_session_key(session_key: str) -> tuple[str, str]:
    """Split `channel:chat_id` into channel/chat_id."""
    if ":" not in session_key:
        return "cli", session_key
    channel, chat_id = session_key.split(":", 1)
    return channel, chat_id


class WorkspaceRuntime:
    """Wrapper around AgentLoop for proactive dispatch in one workspace."""

    def __init__(
        self,
        *,
        workspace: Path,
        workspace_name: str,
        provider: LLMProvider,
        model: str | None,
    ):
        self.workspace = workspace
        self.workspace_name = workspace_name
        self._bus = MessageBus()
        self._agent = AgentLoop(
            bus=self._bus,
            provider=provider,
            workspace=workspace,
            workspace_name=workspace_name,
            model=model,
        )

    async def execute_due_task(self, due: DueTask) -> list[OutboundMessage]:
        """
        Execute one due proactive task through AgentLoop and collect outbound messages.

        Uses `system` channel with chat_id=`channel:chat_id` so AgentLoop routes to
        the canonical target session and outbound channel.
        """
        channel, chat_id = parse_session_key(due.session_key)
        metadata = {"task_id": due.task_id, "proactive": True}

        response_text = await self._agent.process_direct(
            content=due.prompt,
            session_key=due.session_key,
            channel="system",
            chat_id=f"{channel}:{chat_id}",
        )

        outbound: list[OutboundMessage] = []
        if response_text:
            outbound.append(
                OutboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    content=response_text,
                    metadata=metadata,
                )
            )

        while extra := self._bus.try_consume_outbound():
            extra.metadata = {**(extra.metadata or {}), **metadata}
            outbound.append(extra)

        return outbound
