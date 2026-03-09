"""Session management for conversation history."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from atom_agent.logging import get_logger

logger = get_logger("session.manager")


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists, return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str) -> str:
    """Replace unsafe path characters with underscores."""
    import re

    _UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')
    return _UNSAFE_CHARS.sub("_", name).strip()


@dataclass
class Session:
    """
    A conversation session.

    Stores messages in JSONL format for easy reading and persistence.

    Important: Messages are append-only for LLM cache efficiency.
    The consolidation process writes summaries to memory files
    but does NOT modify the messages list or get_history() output.
    """

    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0  # Number of messages already consolidated
    proactive_context: dict[str, Any] = field(default_factory=dict)  # For proactive task context
    workspace_name: str | None = None  # Associated workspace name

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs,
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        """Return unconsolidated messages for LLM input, aligned to a user turn."""
        unconsolidated = self.messages[self.last_consolidated :]
        sliced = unconsolidated[-max_messages:]

        # Drop leading non-user messages to avoid orphaned tool_result blocks
        for i, m in enumerate(sliced):
            if m.get("role") == "user":
                sliced = sliced[i:]
                break

        out: list[dict[str, Any]] = []
        for m in sliced:
            entry: dict[str, Any] = {"role": m["role"], "content": m.get("content", "")}
            for k in ("tool_calls", "tool_call_id", "name"):
                if k in m:
                    entry[k] = m[k]
            out.append(entry)
        return out

    def clear(self) -> None:
        """Clear all messages and reset session to initial state."""
        self.messages = []
        self.last_consolidated = 0
        self.updated_at = datetime.now()

    def set_proactive_context(self, key: str, value: Any) -> None:
        """Set a value in the proactive context."""
        self.proactive_context[key] = value
        self.updated_at = datetime.now()

    def get_proactive_context(self, key: str, default: Any = None) -> Any:
        """Get a value from the proactive context."""
        return self.proactive_context.get(key, default)

    def to_export_dict(self) -> dict[str, Any]:
        """Export session to a dictionary for transfer between workspaces."""
        return {
            "key": self.key,
            "messages": self.messages,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
            "last_consolidated": self.last_consolidated,
            "proactive_context": self.proactive_context,
            "workspace_name": self.workspace_name,
            "export_version": 1,
        }

    @classmethod
    def from_export_dict(cls, data: dict[str, Any]) -> "Session":
        """Create a session from an export dictionary."""
        return cls(
            key=data["key"],
            messages=data.get("messages", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            updated_at=datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(),
            metadata=data.get("metadata", {}),
            last_consolidated=data.get("last_consolidated", 0),
            proactive_context=data.get("proactive_context", {}),
            workspace_name=data.get("workspace_name"),
        )


class SessionManager:
    """
    Manages conversation sessions for a specific workspace.

    Sessions are stored as JSONL files in the workspace's sessions directory.
    Supports session import/export between workspaces.
    """

    def __init__(self, workspace: Path, workspace_name: str | None = None):
        """
        Initialize session manager.

        Args:
            workspace: Path to the workspace directory
            workspace_name: Optional name for the workspace (for metadata)
        """
        self.workspace = workspace
        self.workspace_name = workspace_name or workspace.name
        self.sessions_dir = ensure_dir(self.workspace / "sessions")
        self._cache: dict[str, Session] = {}

    def _get_session_path(self, key: str) -> Path:
        """Get the file path for a session."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / f"{safe_key}.jsonl"

    def get_or_create(self, key: str) -> Session:
        """
        Get an existing session or create a new one.

        Args:
            key: Session key (usually channel:chat_id).

        Returns:
            The session.
        """
        if key in self._cache:
            logger.debug("Session cache hit", extra={"session_key": key})
            return self._cache[key]

        session = self._load(key)
        if session is None:
            session = Session(key=key, workspace_name=self.workspace_name)
            logger.debug("Session created", extra={"session_key": key})
        else:
            logger.debug(
                "Session loaded from disk",
                extra={"session_key": key, "msg_count": len(session.messages)},
            )

        self._cache[key] = session
        return session

    def _load(self, key: str) -> Session | None:
        """Load a session from disk."""
        path = self._get_session_path(key)
        if not path.exists():
            return None

        try:
            messages = []
            metadata = {}
            created_at = None
            last_consolidated = 0
            proactive_context = {}
            workspace_name = None

            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    data = json.loads(line)

                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        created_at = (
                            datetime.fromisoformat(data["created_at"])
                            if data.get("created_at")
                            else None
                        )
                        last_consolidated = data.get("last_consolidated", 0)
                        proactive_context = data.get("proactive_context", {})
                        workspace_name = data.get("workspace_name")
                    else:
                        messages.append(data)

            return Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                metadata=metadata,
                last_consolidated=last_consolidated,
                proactive_context=proactive_context,
                workspace_name=workspace_name,
            )
        except Exception as e:
            logger.warning("Failed to load session", extra={"session_key": key, "error": str(e)})
            return None

    def save(self, session: Session) -> None:
        """Save a session to disk."""
        path = self._get_session_path(session.key)

        try:
            with open(path, "w", encoding="utf-8") as f:
                metadata_line = {
                    "_type": "metadata",
                    "key": session.key,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "metadata": session.metadata,
                    "last_consolidated": session.last_consolidated,
                    "proactive_context": session.proactive_context,
                    "workspace_name": session.workspace_name or self.workspace_name,
                }
                f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")
                for msg in session.messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            logger.debug(
                "Session saved",
                extra={"session_key": session.key, "msg_count": len(session.messages)},
            )
        except Exception as e:
            logger.error(
                "Failed to save session", extra={"session_key": session.key, "error": str(e)}
            )
            raise

        self._cache[session.key] = session

    def invalidate(self, key: str) -> None:
        """Remove a session from the in-memory cache."""
        self._cache.pop(key, None)

    def delete(self, key: str) -> bool:
        """
        Delete a session from disk and cache.

        Args:
            key: Session key to delete

        Returns:
            True if session was deleted, False if not found
        """
        path = self._get_session_path(key)
        self._cache.pop(key, None)

        if path.exists():
            try:
                path.unlink()
                logger.info("Session deleted", extra={"session_key": key})
                return True
            except Exception as e:
                logger.error("Failed to delete session", extra={"session_key": key, "error": str(e)})
                return False

        return False

    def list_sessions(self) -> list[dict[str, Any]]:
        """
        List all sessions.

        Returns:
            List of session info dicts.
        """
        sessions = []

        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                # Read just the metadata line
                with open(path, encoding="utf-8") as f:
                    first_line = f.readline().strip()
                    if first_line:
                        data = json.loads(first_line)
                        if data.get("_type") == "metadata":
                            key = data.get("key") or path.stem.replace("_", ":", 1)
                            sessions.append(
                                {
                                    "key": key,
                                    "created_at": data.get("created_at"),
                                    "updated_at": data.get("updated_at"),
                                    "path": str(path),
                                    "workspace_name": data.get("workspace_name"),
                                }
                            )
            except Exception:
                continue

        return sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)

    def export_session(self, key: str, export_path: Path | None = None) -> Path | None:
        """
        Export a session to a JSON file for transfer to another workspace.

        Args:
            key: Session key to export
            export_path: Optional path for export file (default: {key}.json)

        Returns:
            Path to exported file, or None if session not found
        """
        session = self._load(key)
        if session is None:
            logger.warning("Session not found for export", extra={"session_key": key})
            return None

        if export_path is None:
            export_path = self.workspace / f"{safe_filename(key.replace(':', '_'))}.export.json"

        try:
            with open(export_path, "w", encoding="utf-8") as f:
                json.dump(session.to_export_dict(), f, indent=2, ensure_ascii=False)

            logger.info("Session exported", extra={"session_key": key, "path": str(export_path)})
            return export_path
        except Exception as e:
            logger.error("Failed to export session", extra={"session_key": key, "error": str(e)})
            return None

    def import_session(self, export_path: Path, new_key: str | None = None) -> Session | None:
        """
        Import a session from an export file.

        Args:
            export_path: Path to the export file
            new_key: Optional new key for the session (default: use original key)

        Returns:
            Imported session, or None on failure
        """
        try:
            with open(export_path, encoding="utf-8") as f:
                data = json.load(f)

            session = Session.from_export_dict(data)
            if new_key:
                session.key = new_key

            # Update workspace association
            session.workspace_name = self.workspace_name

            # Save to this workspace
            self.save(session)

            logger.info(
                "Session imported",
                extra={"session_key": session.key, "source_path": str(export_path)},
            )
            return session
        except Exception as e:
            logger.error("Failed to import session", extra={"path": str(export_path), "error": str(e)})
            return None

    def copy_session_to_workspace(
        self, key: str, target_workspace: Path, target_manager: "SessionManager | None" = None
    ) -> Session | None:
        """
        Copy a session to another workspace.

        Args:
            key: Session key to copy
            target_workspace: Target workspace path
            target_manager: Optional SessionManager for target (created if None)

        Returns:
            Copied session in target workspace, or None on failure
        """
        session = self._load(key)
        if session is None:
            logger.warning("Session not found for copy", extra={"session_key": key})
            return None

        if target_manager is None:
            target_manager = SessionManager(target_workspace)

        # Create a copy with updated workspace association
        copied_session = Session(
            key=session.key,
            messages=list(session.messages),
            created_at=session.created_at,
            updated_at=datetime.now(),
            metadata=dict(session.metadata),
            last_consolidated=session.last_consolidated,
            proactive_context=dict(session.proactive_context),
            workspace_name=target_manager.workspace_name,
        )

        # Add source info to metadata
        copied_session.metadata["copied_from"] = self.workspace_name
        copied_session.metadata["copied_at"] = datetime.now().isoformat()

        target_manager.save(copied_session)

        logger.info(
            "Session copied to workspace",
            extra={
                "session_key": key,
                "source_workspace": str(self.workspace),
                "target_workspace": str(target_workspace),
            },
        )

        return copied_session
