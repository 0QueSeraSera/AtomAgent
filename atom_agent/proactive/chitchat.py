"""Chitchat topic generator using LLM and memory context."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from atom_agent.logging import get_logger

if TYPE_CHECKING:
    from atom_agent.memory.store import MemoryStore
    from atom_agent.provider.base import LLMProvider

logger = get_logger("proactive.chitchat")

_CHITCHAT_SYSTEM_PROMPT = """You are a friendly assistant that generates natural, engaging chitchat messages.
Your goal is to build rapport with the user through casual conversation.

Guidelines:
- Keep messages brief (1-2 sentences)
- Be genuinely curious about the user
- Reference past conversations when relevant
- Adapt to the time of day (morning greeting, afternoon check-in, evening wind-down)
- Be warm but not overly familiar
- Ask open-ended questions to encourage conversation
- Avoid being repetitive or robotic"""

_CHITCHAT_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "send_chitchat",
            "description": "Send a chitchat message to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The chitchat message to send (1-2 sentences).",
                    },
                    "topic": {
                        "type": "string",
                        "description": "Brief topic tag (e.g., 'greeting', 'check_in', 'follow_up').",
                    },
                },
                "required": ["message", "topic"],
            },
        },
    }
]


@dataclass
class ChitchatContext:
    """Context for generating chitchat messages."""

    session_key: str
    user_profile: dict[str, Any] = field(default_factory=dict)
    recent_topics: list[str] = field(default_factory=list)
    time_context: dict[str, Any] = field(default_factory=dict)
    conversation_style: str = "friendly"
    preferred_topics: list[str] = field(default_factory=list)

    def to_prompt_context(self) -> str:
        """Build context string for LLM prompt."""
        parts: list[str] = []

        # Time context
        if self.time_context:
            hour = self.time_context.get("hour", 12)
            day_name = self.time_context.get("day_name", "today")
            time_of_day = self._get_time_of_day(hour)
            parts.append(f"Time: {time_of_day} on {day_name} (hour: {hour})")

        # User profile from memory
        if self.user_profile:
            profile_items = [f"- {k}: {v}" for k, v in self.user_profile.items() if v]
            if profile_items:
                parts.append("User info from memory:\n" + "\n".join(profile_items[:5]))

        # Recent conversation topics
        if self.recent_topics:
            topics = ", ".join(self.recent_topics[-3:])
            parts.append(f"Recent topics discussed: {topics}")

        # Preferred topics
        if self.preferred_topics:
            parts.append(f"Preferred topics: {', '.join(self.preferred_topics)}")

        # Style preference
        if self.conversation_style:
            parts.append(f"Conversation style: {self.conversation_style}")

        return "\n\n".join(parts)

    @staticmethod
    def _get_time_of_day(hour: int) -> str:
        """Get time of day description from hour."""
        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"


class ChitchatGenerator:
    """Generate contextual chitchat using LLM and memory."""

    def __init__(
        self,
        provider: LLMProvider,
        memory_store: MemoryStore,
        model: str | None = None,
    ):
        """
        Initialize the chitchat generator.

        Args:
            provider: LLM provider for generating messages
            memory_store: Memory store for retrieving user context
            model: Model to use (default: provider default)
        """
        self.provider = provider
        self.memory_store = memory_store
        self.model = model or provider.get_default_model()

    async def generate_chitchat(
        self,
        context: ChitchatContext,
        base_prompt: str | None = None,
    ) -> str:
        """
        Generate a chitchat message using LLM.

        Args:
            context: Chitchat context with user info and preferences
            base_prompt: Optional base prompt to guide generation

        Returns:
            Generated chitchat message
        """
        import json

        prompt_context = context.to_prompt_context()
        user_prompt = base_prompt or "Generate a friendly message to start or continue a conversation."

        full_prompt = f"""{user_prompt}

## Context
{prompt_context}

Generate an appropriate chitchat message using the send_chitchat tool."""

        try:
            response = await self.provider.chat(
                messages=[
                    {"role": "system", "content": _CHITCHAT_SYSTEM_PROMPT},
                    {"role": "user", "content": full_prompt},
                ],
                tools=_CHITCHAT_TOOL,
                model=self.model,
                temperature=0.8,  # Higher temperature for more variety
            )

            if not response.has_tool_calls:
                # Fallback to response content if no tool call
                logger.warning(
                    "Chitchat generation returned no tool call, using content",
                    extra={"session_key": context.session_key},
                )
                return response.content or "Hey! How's it going?"

            args = response.tool_calls[0].arguments
            if isinstance(args, str):
                args = json.loads(args)
            if isinstance(args, list) and args and isinstance(args[0], dict):
                args = args[0]

            message = args.get("message", "")
            if not isinstance(message, str) or not message.strip():
                return "Hey! How's it going?"

            logger.info(
                "Chitchat generated",
                extra={
                    "session_key": context.session_key,
                    "topic": args.get("topic", "unknown"),
                },
            )
            return message.strip()

        except Exception as e:
            logger.error(
                "Chitchat generation failed",
                extra={"session_key": context.session_key, "error": str(e)},
            )
            return "Hey! How's it going?"

    async def build_context_from_memory(
        self,
        chat_id: str,
        session_key: str,
        chitchat_config: dict[str, Any] | None = None,
    ) -> ChitchatContext:
        """
        Build chitchat context by searching memory for user info.

        Args:
            chat_id: Feishu chat ID
            session_key: Full session key
            chitchat_config: Optional chitchat configuration

        Returns:
            ChitchatContext with user info from memory
        """
        now = datetime.now()
        time_context = {
            "hour": now.hour,
            "day_of_week": now.weekday(),
            "day_name": now.strftime("%A"),
            "date": now.strftime("%Y-%m-%d"),
        }

        user_profile: dict[str, Any] = {}
        recent_topics: list[str] = []

        # Search memory for user-related information
        try:
            # Search for user preferences, interests, etc.
            searches = [
                ("user preferences interests hobbies", "global"),
                (f"chat {chat_id}", "all"),
            ]

            for query, scope in searches:
                results = self.memory_store.search(
                    query,
                    scope=scope,  # type: ignore
                    limit=3,
                    snippet_chars=200,
                )
                for result in results:
                    snippet = result.get("snippet", "")
                    if snippet:
                        # Extract topics from snippets
                        recent_topics.append(snippet[:50])

        except Exception as e:
            logger.warning(
                "Failed to search memory for chitchat context",
                extra={"session_key": session_key, "error": str(e)},
            )

        # Apply config preferences
        config = chitchat_config or {}
        conversation_style = config.get("style", "friendly")
        preferred_topics = config.get("topics", [])

        return ChitchatContext(
            session_key=session_key,
            user_profile=user_profile,
            recent_topics=recent_topics[:5],
            time_context=time_context,
            conversation_style=conversation_style,
            preferred_topics=preferred_topics,
        )
