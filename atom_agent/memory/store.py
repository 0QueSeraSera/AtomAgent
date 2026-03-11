"""Memory system for persistent agent memory."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from atom_agent.logging import get_logger

if TYPE_CHECKING:
    from atom_agent.provider.base import LLMProvider
    from atom_agent.session.manager import Session

logger = get_logger("memory.store")


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists, return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


_SAVE_MEMORY_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Save the memory consolidation result to persistent storage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "history_entry": {
                        "type": "string",
                        "description": "A paragraph (2-5 sentences) summarizing key events/decisions/topics. "
                        "Start with [YYYY-MM-DD HH:MM]. Include detail useful for grep search.",
                    },
                    "memory_update": {
                        "type": "string",
                        "description": "Full updated long-term memory as markdown. Include all existing "
                        "facts plus new ones. Return unchanged if nothing new.",
                    },
                },
                "required": ["history_entry", "memory_update"],
            },
        },
    }
]


class MemoryStore:
    """Two-layer memory: MEMORY.md (long-term facts) + HISTORY.md (grep-searchable log)."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.memory_dir = ensure_dir(workspace / "memory")
        self.memory_file = self.memory_dir / "MEMORY.md"
        self.history_file = self.memory_dir / "HISTORY.md"
        self.global_dir = ensure_dir(self.memory_dir / "global")
        self.projects_dir = ensure_dir(self.memory_dir / "projects")
        self.global_brief_file = self.global_dir / "BRIEF.md"

    @staticmethod
    def sanitize_project_id(project_id: str) -> str:
        """Normalize project id into a safe directory name."""
        normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", project_id.strip())
        normalized = normalized.strip("-._")
        return normalized[:80] if normalized else "default"

    def resolve_project_id(self, project_id: str | None = None) -> str:
        """Resolve project id from explicit value or workspace name."""
        if project_id and project_id.strip():
            return self.sanitize_project_id(project_id)
        return self.sanitize_project_id(self.workspace.name)

    def get_project_dir(self, project_id: str | None = None) -> Path:
        """Return project memory directory, creating it if needed."""
        return ensure_dir(self.projects_dir / self.resolve_project_id(project_id))

    def get_project_brief_path(self, project_id: str | None = None) -> Path:
        """Return BRIEF.md path for project memory."""
        return self.get_project_dir(project_id) / "BRIEF.md"

    def read_global_brief(self) -> str:
        """Read global brief, falling back to legacy MEMORY.md."""
        if self.global_brief_file.exists():
            return self.global_brief_file.read_text(encoding="utf-8")
        return self.read_long_term()

    def read_project_brief(self, project_id: str | None = None) -> str:
        """Read project brief markdown."""
        brief_path = self.get_project_brief_path(project_id)
        if brief_path.exists():
            return brief_path.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def _compact_markdown(text: str, *, max_lines: int, max_chars: int) -> str:
        """Compact markdown text into a bounded brief for prompt usage."""
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""

        compact: list[str] = []
        total_chars = 0
        for line in lines:
            if len(compact) >= max_lines:
                break
            line_chars = len(line)
            if total_chars + line_chars > max_chars:
                remaining = max_chars - total_chars
                if remaining > 24:
                    compact.append(line[:remaining].rstrip() + "...")
                break
            compact.append(line)
            total_chars += line_chars

        return "\n".join(compact).strip()

    def build_prompt_brief(self, project_id: str | None = None) -> str:
        """
        Build brief-only memory context for prompt injection.

        This intentionally avoids injecting full project memory content.
        """
        sections: list[str] = []

        global_brief = self._compact_markdown(
            self.read_global_brief(),
            max_lines=12,
            max_chars=1800,
        )
        if global_brief:
            sections.append("## Global Memory Brief\n" + global_brief)

        resolved_project_id = self.resolve_project_id(project_id) if project_id else None
        if resolved_project_id:
            project_brief = self._compact_markdown(
                self.read_project_brief(resolved_project_id),
                max_lines=14,
                max_chars=2200,
            )
            if project_brief:
                sections.append(f"## Project Memory Brief ({resolved_project_id})\n" + project_brief)

        return "\n\n".join(sections).strip()

    def read_long_term(self) -> str:
        """Read the long-term memory file."""
        if self.memory_file.exists():
            return self.memory_file.read_text(encoding="utf-8")
        return ""

    def write_long_term(self, content: str) -> None:
        """Write to the long-term memory file."""
        self.memory_file.write_text(content, encoding="utf-8")

    def append_history(self, entry: str) -> None:
        """Append an entry to the history log."""
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(entry.rstrip() + "\n\n")

    def get_memory_context(self) -> str:
        """Get the memory context for the system prompt."""
        long_term = self.read_long_term()
        return f"## Long-term Memory\n{long_term}" if long_term else ""

    async def consolidate(
        self,
        session: Session,
        provider: LLMProvider,
        model: str,
        *,
        archive_all: bool = False,
        memory_window: int = 50,
    ) -> bool:
        """Consolidate old messages into MEMORY.md + HISTORY.md via LLM tool call.

        Returns True on success (including no-op), False on failure.
        """
        if archive_all:
            old_messages = session.messages
            keep_count = 0
        else:
            keep_count = memory_window // 2
            if len(session.messages) <= keep_count:
                return True
            if len(session.messages) - session.last_consolidated <= 0:
                return True
            old_messages = session.messages[session.last_consolidated : -keep_count]
            if not old_messages:
                return True

        logger.info(
            "Memory consolidation starting",
            extra={
                "session_key": session.key,
                "msg_count": len(old_messages),
                "archive_all": archive_all,
            },
        )

        lines = []
        for m in old_messages:
            if not m.get("content"):
                continue
            tools = f" [tools: {', '.join(m['tools_used'])}]" if m.get("tools_used") else ""
            lines.append(
                f"[{m.get('timestamp', '?')[:16]}] {m['role'].upper()}{tools}: {m['content']}"
            )

        current_memory = self.read_long_term()
        prompt = f"""Process this conversation and call the save_memory tool with your consolidation.

## Current Long-term Memory
{current_memory or "(empty)"}

## Conversation to Process
{chr(10).join(lines)}"""

        try:
            response = await provider.chat(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a memory consolidation agent. Call the save_memory tool with your consolidation of the conversation.",
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=_SAVE_MEMORY_TOOL,
                model=model,
            )

            if not response.has_tool_calls:
                logger.warning(
                    "Memory consolidation failed: no tool call",
                    extra={"session_key": session.key},
                )
                return False

            args = response.tool_calls[0].arguments
            # Some providers return arguments as a JSON string instead of dict
            if isinstance(args, str):
                args = json.loads(args)
            # Some providers return arguments as a list (handle edge case)
            if isinstance(args, list):
                if args and isinstance(args[0], dict):
                    args = args[0]
                else:
                    return False
            if not isinstance(args, dict):
                return False

            if entry := args.get("history_entry"):
                if not isinstance(entry, str):
                    entry = json.dumps(entry, ensure_ascii=False)
                self.append_history(entry)
            if update := args.get("memory_update"):
                if not isinstance(update, str):
                    update = json.dumps(update, ensure_ascii=False)
                if update != current_memory:
                    self.write_long_term(update)

            session.last_consolidated = 0 if archive_all else len(session.messages) - keep_count
            logger.info(
                "Memory consolidation complete",
                extra={"session_key": session.key, "last_consolidated": session.last_consolidated},
            )
            return True
        except Exception as e:
            logger.error(
                "Memory consolidation failed",
                extra={"session_key": session.key, "error": str(e)},
            )
            return False
