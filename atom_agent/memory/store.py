"""Memory system for persistent agent memory."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

    def get_project_dir(self, project_id: str | None = None, *, create: bool = True) -> Path:
        """Return project memory directory, creating it if needed."""
        project_dir = self.projects_dir / self.resolve_project_id(project_id)
        return ensure_dir(project_dir) if create else project_dir

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

    @staticmethod
    def _safe_filename(name: str) -> str | None:
        """Return sanitized basename if safe for local memory lookup."""
        if not name or "/" in name or "\\" in name:
            return None
        if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
            return None
        return name

    @staticmethod
    def _read_text(path: Path) -> str:
        """Read text file safely with replacement for decode errors."""
        return path.read_text(encoding="utf-8", errors="replace")

    @staticmethod
    def _build_snippet(text: str, terms: list[str], *, max_chars: int) -> str:
        """Build a concise snippet around the earliest matched term."""
        compact = " ".join(line.strip() for line in text.splitlines() if line.strip())
        if not compact:
            return ""
        if len(compact) <= max_chars:
            return compact

        lower = compact.lower()
        matches = [lower.find(term) for term in terms if term]
        matches = [idx for idx in matches if idx >= 0]
        start = max(0, min(matches) - (max_chars // 3)) if matches else 0
        end = min(len(compact), start + max_chars)
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(compact) else ""
        return f"{prefix}{compact[start:end].strip()}{suffix}"

    def _iter_memory_entries(
        self,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> list[tuple[str, Path]]:
        """Collect memory entries by scope."""
        entries: list[tuple[str, Path]] = []
        include_global = scope in {"all", "global"}
        include_project = scope in {"all", "project", "active_project"}

        if include_global:
            fixed = [
                ("global:BRIEF.md", self.global_brief_file),
                ("global:MEMORY.md", self.memory_file),
                ("global:HISTORY.md", self.history_file),
            ]
            for memory_id, path in fixed:
                if path.exists():
                    entries.append((memory_id, path))

            for path in sorted(self.global_dir.glob("*.md")):
                if path.name == "BRIEF.md":
                    continue
                safe = self._safe_filename(path.name)
                if safe:
                    entries.append((f"global:{safe}", path))

        if include_project:
            effective_id = self.resolve_project_id(project_id)
            project_dir = self.get_project_dir(effective_id, create=False)
            if project_dir.exists():
                for path in sorted(project_dir.iterdir()):
                    if not path.is_file():
                        continue
                    safe = self._safe_filename(path.name)
                    if not safe:
                        continue
                    entries.append((f"project:{effective_id}:{safe}", path))

        return entries

    def search(
        self,
        query: str,
        *,
        scope: str = "all",
        project_id: str | None = None,
        limit: int = 5,
        snippet_chars: int = 280,
    ) -> list[dict[str, Any]]:
        """Search memory entries and return ranked handles/snippets."""
        query = query.strip()
        terms = [term.lower() for term in re.findall(r"[A-Za-z0-9_.-]+", query) if term]
        candidates = self._iter_memory_entries(scope=scope, project_id=project_id)
        ranked: list[tuple[int, float, dict[str, Any]]] = []

        for memory_id, path in candidates:
            try:
                text = self._read_text(path)
            except OSError:
                continue

            haystack = text.lower()
            score = sum(haystack.count(term) for term in terms) if terms else 1
            if score <= 0:
                continue

            snippet = self._build_snippet(text, terms, max_chars=snippet_chars)
            item = {
                "memory_id": memory_id,
                "title": path.name,
                "snippet": snippet,
            }
            mtime = path.stat().st_mtime
            ranked.append((score, mtime, item))

        ranked.sort(key=lambda row: (-row[0], -row[1], row[2]["memory_id"]))
        return [item for _, _, item in ranked[: max(1, min(limit, 20))]]

    def resolve_memory_id(self, memory_id: str) -> Path | None:
        """Resolve a memory handle into a file path."""
        if memory_id.startswith("global:"):
            filename = self._safe_filename(memory_id.split(":", 1)[1])
            if not filename:
                return None
            if filename == "MEMORY.md":
                return self.memory_file
            if filename == "HISTORY.md":
                return self.history_file
            return self.global_dir / filename

        if memory_id.startswith("project:"):
            parts = memory_id.split(":", 2)
            if len(parts) != 3:
                return None
            project_id = self.sanitize_project_id(parts[1])
            filename = self._safe_filename(parts[2])
            if not filename:
                return None
            return self.get_project_dir(project_id, create=False) / filename

        return None

    def read_entry(self, memory_id: str, *, max_chars: int = 8000) -> dict[str, Any] | None:
        """Read a memory entry by handle, with output truncation."""
        path = self.resolve_memory_id(memory_id)
        if path is None or not path.exists() or not path.is_file():
            return None

        try:
            content = self._read_text(path)
        except OSError:
            return None

        truncated = False
        if len(content) > max_chars:
            content = content[:max_chars].rstrip() + "\n\n...[truncated]"
            truncated = True

        return {
            "memory_id": memory_id,
            "path": str(path),
            "content": content,
            "truncated": truncated,
        }

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
