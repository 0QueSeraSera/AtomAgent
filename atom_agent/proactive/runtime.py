"""Runtime helpers for proactive task dispatch."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from atom_agent.bus.events import InboundMessage
from atom_agent.proactive.models import DueTask

if TYPE_CHECKING:
    from atom_agent.proactive.chitchat import ChitchatGenerator


def parse_session_key(session_key: str) -> tuple[str, str]:
    """Split `channel:chat_id` into channel/chat_id."""
    if ":" not in session_key:
        return "cli", session_key
    channel, chat_id = session_key.split(":", 1)
    return channel, chat_id


def resolve_due_target(due: DueTask) -> tuple[str, str, dict[str, Any]]:
    """Resolve delivery target and metadata for a due proactive task."""
    if due.target is not None:
        metadata: dict[str, Any] = {}
        if due.target.reply_to:
            metadata["reply_to"] = due.target.reply_to
        if due.target.thread_id:
            metadata["thread_id"] = due.target.thread_id
        return due.target.channel, due.target.chat_id, metadata

    channel, chat_id = parse_session_key(due.session_key)
    return channel, chat_id, {}


def build_due_inbound_message(due: DueTask) -> InboundMessage:
    """
    Build a high-priority system inbound message for one due proactive task.

    - Delivery target is encoded in `chat_id` as `channel:chat_id`.
    - Memory scope remains `due.session_key` via `session_key_override`.
    """
    channel, chat_id, target_metadata = resolve_due_target(due)
    metadata: dict[str, Any] = {
        "task_id": due.task_id,
        "proactive": True,
        "scheduled_time": due.scheduled_time.isoformat(),
        "base_time": due.base_time.isoformat(),
        **target_metadata,
    }

    # Add chitchat metadata if enabled
    if due.chitchat_mode:
        metadata["chitchat_mode"] = True
        metadata["chitchat_context"] = due.chitchat_context

    return InboundMessage(
        channel="system",
        sender_id=f"proactive:{due.task_id}",
        chat_id=f"{channel}:{chat_id}",
        content=due.prompt,
        metadata=metadata,
        session_key_override=due.session_key,
        priority="high",
    )


async def build_chitchat_inbound_message(
    due: DueTask,
    chitchat_generator: ChitchatGenerator | None = None,
) -> InboundMessage:
    """
    Build message with LLM-generated chitchat content.

    If chitchat_generator is provided, generates contextual chitchat.
    Otherwise, falls back to static prompt.

    Args:
        due: The due task with chitchat configuration
        chitchat_generator: Optional generator for LLM-based content

    Returns:
        InboundMessage with generated or static content
    """
    from atom_agent.proactive.chitchat import ChitchatContext

    channel, chat_id, target_metadata = resolve_due_target(due)

    # Generate chitchat content if generator is available
    if chitchat_generator is not None:
        # Build context from memory
        context = await chitchat_generator.build_context_from_memory(
            chat_id=chat_id,
            session_key=due.session_key,
            chitchat_config=due.chitchat_context,
        )

        # Generate chitchat message
        content = await chitchat_generator.generate_chitchat(
            context=context,
            base_prompt=due.prompt,
        )
    else:
        # Fallback to static prompt
        content = due.prompt

    metadata: dict[str, Any] = {
        "task_id": due.task_id,
        "proactive": True,
        "chitchat_mode": True,
        "scheduled_time": due.scheduled_time.isoformat(),
        "base_time": due.base_time.isoformat(),
        **target_metadata,
    }

    return InboundMessage(
        channel="system",
        sender_id=f"proactive:{due.task_id}",
        chat_id=f"{channel}:{chat_id}",
        content=content,
        metadata=metadata,
        session_key_override=due.session_key,
        priority="high",
    )
