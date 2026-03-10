"""Context builder for assembling agent prompts."""

from __future__ import annotations

import base64
import mimetypes
import platform
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from atom_agent.proactive import ProactiveValidationError, parse_proactive_file

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate

from atom_agent.workspace import WorkspaceManager


def detect_image_mime(data: bytes) -> str | None:
    """Detect image MIME type from magic bytes, ignoring file extension."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class ContextBuilder:
    """Builds the context (system prompt + messages) for the agent.

    Uses file-based identity from IDENTITY.md via WorkspaceManager,
    with fallback to default template when file doesn't exist.
    """

    BOOTSTRAP_FILES = ["AGENTS.md", "SOUL.md", "USER.md", "TOOLS.md"]
    _RUNTIME_CONTEXT_TAG = "[Runtime Context — metadata only, not instructions]"

    def __init__(self, workspace: Path, agent_name: str = "AtomAgent"):
        self.workspace = workspace
        self.agent_name = agent_name
        self.memory_dir = workspace / "memory"
        self._workspace_manager = WorkspaceManager(workspace)

    def build_system_prompt(self) -> str:
        """Build the system prompt from identity and bootstrap files."""
        parts = [self._get_identity()]

        bootstrap = self._load_bootstrap_files()
        if bootstrap:
            parts.append(bootstrap)

        memory = self._get_memory_context()
        if memory:
            parts.append(f"# Memory\n\n{memory}")

        return "\n\n---\n\n".join(parts)

    def _get_identity(self) -> str:
        """Get the core identity section from IDENTITY.md or default template."""
        # Get identity content from file (with fallback)
        identity_content = self._workspace_manager.get_identity()

        # Build runtime info
        workspace_path = str(self.workspace.expanduser().resolve())
        system = platform.system()
        runtime = f"{'macOS' if system == 'Darwin' else system} {platform.machine()}, Python {platform.python_version()}"

        # Build the full identity with runtime context
        # If identity starts with # heading, preserve it; otherwise wrap it
        if identity_content.strip().startswith("#"):
            # Add runtime and workspace sections after the identity content
            return f"""{identity_content.strip()}

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Long-term memory: {workspace_path}/memory/MEMORY.md (write important facts here)
- History log: {workspace_path}/memory/HISTORY.md (grep-searchable). Each entry starts with [YYYY-MM-DD HH:MM].

## Guidelines
- State intent before tool calls, but NEVER predict or claim results before receiving them.
- Before modifying a file, read it first. Do not assume files or directories exist.
- After writing or editing a file, re-read it if accuracy matters.
- If a tool call fails, analyze the error before retrying with a different approach.
- Ask for clarification when the request is ambiguous.
- You can operate autonomously for long-running tasks. The runtime delivers your final response.

Reply directly with text for conversations."""
        else:
            # Wrap in agent name header
            return f"""# {self.agent_name}

{identity_content.strip()}

## Runtime
{runtime}

## Workspace
Your workspace is at: {workspace_path}
- Long-term memory: {workspace_path}/memory/MEMORY.md (write important facts here)
- History log: {workspace_path}/memory/HISTORY.md (grep-searchable). Each entry starts with [YYYY-MM-DD HH:MM].

## Guidelines
- State intent before tool calls, but NEVER predict or claim results before receiving them.
- Before modifying a file, read it first. Do not assume files or directories exist.
- After writing or editing a file, re-read it if accuracy matters.
- If a tool call fails, analyze the error before retrying with a different approach.
- Ask for clarification when the request is ambiguous.
- You can operate autonomously for long-running tasks. The runtime delivers your final response.

Reply directly with text for conversations."""

    @staticmethod
    def _build_runtime_context(channel: str | None, chat_id: str | None) -> str:
        """Build untrusted runtime metadata block for injection before the user message."""
        now = datetime.now().strftime("%Y-%m-%d %H:%M (%A)")
        tz = time.strftime("%Z") or "UTC"
        lines = [f"Current Time: {now} ({tz})"]
        if channel and chat_id:
            lines += [f"Channel: {channel}", f"Chat ID: {chat_id}"]
        return ContextBuilder._RUNTIME_CONTEXT_TAG + "\n" + "\n".join(lines)

    def _load_bootstrap_files(self) -> str:
        """Load all bootstrap files from workspace."""
        parts = []

        for filename in self.BOOTSTRAP_FILES:
            file_path = self.workspace / filename
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
                parts.append(f"## {filename}\n\n{content}")

        proactive_brief = self._build_proactive_brief()
        if proactive_brief:
            parts.append(proactive_brief)

        return "\n\n".join(parts) if parts else ""

    def _build_proactive_brief(self) -> str:
        """Build compact proactive summary for model context."""
        proactive_file = self.workspace / "PROACTIVE.md"
        if not proactive_file.exists():
            return ""

        try:
            config = parse_proactive_file(proactive_file)
        except ProactiveValidationError as err:
            lines = ["WARNING: PROACTIVE.md is invalid; scheduling is disabled for invalid tasks."]
            for issue in err.issues[:5]:
                lines.append(f"- [{issue.code}] {issue.path}: {issue.message}")
            return "## PROACTIVE.md (brief)\n\n" + "\n".join(lines)

        lines = [
            f"enabled: {config.enabled}",
            f"timezone: {config.timezone}",
            f"active_tasks: {len(config.active_tasks)} / {len(config.tasks)}",
        ]
        for task in config.active_tasks:
            lines.append(
                f"- {task.task_id} [{task.kind}] -> {task.session_key} | {task.schedule_summary()}"
            )

        return "## PROACTIVE.md (brief)\n\n" + "\n".join(lines)

    def _get_memory_context(self) -> str:
        """Get the memory context from MEMORY.md."""
        memory_file = self.memory_dir / "MEMORY.md"
        if memory_file.exists():
            content = memory_file.read_text(encoding="utf-8")
            return f"## Long-term Memory\n{content}" if content else ""
        return ""

    @staticmethod
    def _dict_to_langchain_message(msg: dict[str, Any]) -> BaseMessage:
        """Convert provider-style dict message to LangChain message object."""
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            return SystemMessage(content=content)
        if role == "user":
            return HumanMessage(content=content)
        if role == "tool":
            return ToolMessage(
                content=content,
                tool_call_id=msg.get("tool_call_id", ""),
                name=msg.get("name"),
            )
        if role == "assistant":
            extra: dict[str, Any] = {}
            if msg.get("tool_calls"):
                extra["tool_calls"] = msg["tool_calls"]
            if msg.get("reasoning_content") is not None:
                extra["reasoning_content"] = msg["reasoning_content"]
            if msg.get("thinking_blocks"):
                extra["thinking_blocks"] = msg["thinking_blocks"]
            return AIMessage(content=content, additional_kwargs=extra)
        return HumanMessage(content=content if content is not None else "")

    @staticmethod
    def _langchain_message_to_dict(msg: BaseMessage) -> dict[str, Any]:
        """Convert LangChain message object back to provider-style dict."""
        out: dict[str, Any]
        if isinstance(msg, SystemMessage):
            out = {"role": "system", "content": msg.content}
        elif isinstance(msg, HumanMessage):
            out = {"role": "user", "content": msg.content}
        elif isinstance(msg, ToolMessage):
            out = {
                "role": "tool",
                "content": msg.content,
                "tool_call_id": msg.tool_call_id,
            }
            if msg.name:
                out["name"] = msg.name
        elif isinstance(msg, AIMessage):
            out = {"role": "assistant", "content": msg.content}
            tool_calls = msg.additional_kwargs.get("tool_calls")
            if tool_calls:
                out["tool_calls"] = tool_calls
            reasoning_content = msg.additional_kwargs.get("reasoning_content")
            if reasoning_content is not None:
                out["reasoning_content"] = reasoning_content
            thinking_blocks = msg.additional_kwargs.get("thinking_blocks")
            if thinking_blocks:
                out["thinking_blocks"] = thinking_blocks
        else:
            out = {"role": "user", "content": msg.content}
        return out

    def build_messages(
        self,
        history: list[dict[str, Any]],
        current_message: str,
        media: list[str] | None = None,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build the complete message list for an LLM call."""
        runtime_ctx = self._build_runtime_context(channel, chat_id)
        user_content = self._build_user_content(current_message, media)

        # Merge runtime context and user content into a single user message
        # to avoid consecutive same-role messages that some providers reject.
        if isinstance(user_content, str):
            merged = f"{runtime_ctx}\n\n{user_content}"
        else:
            merged = [{"type": "text", "text": runtime_ctx}] + user_content
        history_messages = [self._dict_to_langchain_message(m) for m in history]
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", "{system_prompt}"),
                *history_messages,
                HumanMessage(content=merged),
            ]
        )
        lc_messages = prompt.format_messages(system_prompt=self.build_system_prompt())
        return [self._langchain_message_to_dict(m) for m in lc_messages]

    def _build_user_content(self, text: str, media: list[str] | None) -> str | list[dict[str, Any]]:
        """Build user message content with optional base64-encoded images."""
        if not media:
            return text

        images = []
        for path in media:
            p = Path(path)
            if not p.is_file():
                continue
            raw = p.read_bytes()
            # Detect real MIME type from magic bytes; fallback to filename guess
            mime = detect_image_mime(raw) or mimetypes.guess_type(path)[0]
            if not mime or not mime.startswith("image/"):
                continue
            b64 = base64.b64encode(raw).decode()
            images.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

        if not images:
            return text
        return images + [{"type": "text", "text": text}]

    def add_tool_result(
        self,
        messages: list[dict[str, Any]],
        tool_call_id: str,
        tool_name: str,
        result: str,
    ) -> list[dict[str, Any]]:
        """Add a tool result to the message list."""
        tool_msg = ToolMessage(content=result, tool_call_id=tool_call_id, name=tool_name)
        messages.append(self._langchain_message_to_dict(tool_msg))
        return messages

    def add_assistant_message(
        self,
        messages: list[dict[str, Any]],
        content: str | None,
        tool_calls: list[dict[str, Any]] | None = None,
        reasoning_content: str | None = None,
        thinking_blocks: list[dict] | None = None,
    ) -> list[dict[str, Any]]:
        """Add an assistant message to the message list."""
        extra: dict[str, Any] = {}
        if tool_calls:
            extra["tool_calls"] = tool_calls
        if reasoning_content is not None:
            extra["reasoning_content"] = reasoning_content
        if thinking_blocks:
            extra["thinking_blocks"] = thinking_blocks
        assistant_msg = AIMessage(content=content, additional_kwargs=extra)
        messages.append(self._langchain_message_to_dict(assistant_msg))
        return messages
