"""Agent loop: the core processing engine for proactive, long-running agents."""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import weakref
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from atom_agent.agent.context import ContextBuilder
from atom_agent.bus.events import InboundMessage, OutboundMessage
from atom_agent.bus.queue import MessageBus, ProactiveScheduler
from atom_agent.logging import get_logger, set_session_key, trace_context
from atom_agent.mcp import MCPClientManager
from atom_agent.memory.store import MemoryStore
from atom_agent.provider.base import LLMProvider
from atom_agent.session.manager import Session, SessionManager
from atom_agent.skills import SkillsLoader
from atom_agent.tools.bash import BashTool
from atom_agent.tools.fetch import FetchTool
from atom_agent.tools.memory import MemoryReadTool, MemorySearchTool
from atom_agent.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from atom_agent.bus.events import ProactiveTask

logger = get_logger("agent.loop")

try:
    from langsmith.run_helpers import trace as langsmith_trace
except ImportError:  # pragma: no cover - optional dependency
    langsmith_trace = None


class AgentLoop:
    """
    The agent loop is the core processing engine.

    It:
    1. Receives messages from the bus
    2. Builds context with history, memory
    3. Calls the LLM
    4. Executes tool calls
    5. Sends responses back

    Features for proactivity and long-running operation:
    - Priority-based message processing
    - Background memory consolidation
    - Proactive task scheduling
    - Task cancellation support
    - Workspace-aware session management
    """

    _TOOL_RESULT_MAX_CHARS = 500

    def __init__(
        self,
        bus: MessageBus,
        provider: LLMProvider,
        workspace: Path,
        model: str | None = None,
        max_iterations: int = 40,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        memory_window: int = 100,
        reasoning_effort: str | None = None,
        agent_name: str = "AtomAgent",
        session_manager: SessionManager | None = None,
        workspace_name: str | None = None,
    ):
        """
        Initialize the agent loop.

        Args:
            bus: Message bus for communication
            provider: LLM provider instance
            workspace: Path to the workspace directory
            model: Model to use (default: provider default)
            max_iterations: Maximum tool call iterations per message
            temperature: Temperature for LLM calls
            max_tokens: Maximum tokens for LLM responses
            memory_window: Number of messages before consolidation
            reasoning_effort: Reasoning effort setting
            agent_name: Name of the agent
            session_manager: Optional session manager (created if None)
            workspace_name: Optional workspace name (derived from path if None)
        """
        self.bus = bus
        self.provider = provider
        self.workspace = workspace
        self.workspace_name = workspace_name or workspace.name
        self.model = model or provider.get_default_model()
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.memory_window = memory_window
        self.reasoning_effort = reasoning_effort
        self.agent_name = agent_name

        self.context = ContextBuilder(workspace, agent_name)
        self.sessions = session_manager or SessionManager(workspace, self.workspace_name)
        self.tools = ToolRegistry()
        self._mcp = self._create_mcp_manager(workspace)
        self.scheduler = ProactiveScheduler(bus)

        self._running = False
        self._consolidating: set[str] = set()  # Session keys with consolidation in progress
        self._consolidation_tasks: set[asyncio.Task] = set()  # Strong refs to in-flight tasks
        self._consolidation_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._active_tasks: dict[str, list[asyncio.Task]] = {}  # session_key -> tasks
        self._processing_lock = asyncio.Lock()
        self._workspace_lock = asyncio.Lock()  # Lock for workspace switching
        self._register_default_tools()

    def _create_mcp_manager(self, workspace: Path) -> MCPClientManager:
        """Create MCP manager instance bound to a workspace."""
        return MCPClientManager(workspace=workspace, registry=self.tools)

    def _register_default_tools(self) -> None:
        """Register the default model-facing tool set."""
        self.tools.register(FetchTool(default_timeout=30.0))
        self.tools.register(
            MemorySearchTool(workspace=self.workspace, default_project_id=self.workspace_name)
        )
        self.tools.register(MemoryReadTool(workspace=self.workspace))
        self.tools.register(
            BashTool(
                default_timeout=60.0,
                blocked_commands=["rm", "sudo", "mkfs"],
                default_cwd=str(self.workspace),
            )
        )

    def register_tool(self, tool: Any) -> None:
        """Register a custom tool."""
        if getattr(tool, "name", None) == "message":
            raise ValueError(
                "Tool 'message' is not model-facing. Use AgentLoop.send_proactive_message()."
            )
        self.tools.register(tool)

    def unregister_tool(self, name: str) -> None:
        """Unregister a tool by name."""
        self.tools.unregister(name)

    def register_proactive_task(self, task: ProactiveTask) -> None:
        """Register a proactive task for scheduled execution."""
        self.scheduler.register_task(task)

    def unregister_proactive_task(self, task_id: str) -> None:
        """Unregister a proactive task."""
        self.scheduler.unregister_task(task_id)

    async def switch_workspace(
        self, new_workspace: Path, workspace_name: str | None = None
    ) -> bool:
        """
        Switch to a different workspace at runtime.

        This will:
        - Save any pending sessions
        - Load the new workspace configuration
        - Rebuild context with new identity

        Args:
            new_workspace: Path to the new workspace
            workspace_name: Optional name for the workspace

        Returns:
            True if switch was successful
        """
        async with self._workspace_lock:
            try:
                logger.info(
                    "Switching workspace",
                    extra={
                        "from": str(self.workspace),
                        "to": str(new_workspace),
                    },
                )

                # Validate new workspace
                if not new_workspace.exists():
                    logger.warning("Target workspace does not exist", extra={"path": str(new_workspace)})
                    return False

                # Update workspace
                self.workspace = new_workspace
                self.workspace_name = workspace_name or new_workspace.name

                # Rebuild context
                self.context = ContextBuilder(new_workspace, self.agent_name)

                # Create new session manager for the workspace
                self.sessions = SessionManager(new_workspace, self.workspace_name)
                await self._close_mcp_tools()
                self._mcp = self._create_mcp_manager(new_workspace)
                await self._connect_mcp_tools()

                logger.info(
                    "Workspace switched",
                    extra={
                        "workspace": str(self.workspace),
                        "workspace_name": self.workspace_name,
                    },
                )

                return True
            except Exception as e:
                logger.error(
                    "Failed to switch workspace",
                    extra={"error": str(e), "path": str(new_workspace)},
                )
                return False

    def get_workspace_info(self) -> dict[str, Any]:
        """
        Get information about the current workspace.

        Returns:
            Dict with workspace information
        """
        skills = SkillsLoader(self.workspace).list_skills(include_disabled=True)
        enabled_skills = sum(1 for item in skills if item.enabled)
        return {
            "path": str(self.workspace),
            "name": self.workspace_name,
            "agent_name": self.agent_name,
            "model": self.model,
            "sessions": len(self.sessions.list_sessions()),
            "tools": self.tools.tool_names,
            "skills": {"installed": len(skills), "enabled": enabled_skills},
            "mcp": {
                "servers": self._mcp.connected_servers,
                "tools": self._mcp.registered_tool_names,
            },
        }

    async def _connect_mcp_tools(self) -> None:
        """Load MCP tools from workspace config."""
        tool_names = await self._mcp.connect_from_workspace()
        if tool_names:
            logger.info(
                "MCP tools loaded",
                extra={
                    "workspace": self.workspace_name,
                    "mcp_servers": self._mcp.connected_servers,
                    "mcp_tools": tool_names,
                },
            )

    async def _close_mcp_tools(self) -> None:
        """Unload MCP tools and close MCP sessions."""
        await self._mcp.close()

    @staticmethod
    def _strip_think(text: str | None) -> str | None:
        """Remove <think…</think blocks that some models embed in content."""
        if not text:
            return None
        return re.sub(r"<think[\s\S]*?</think ", "", text).strip() or None

    @staticmethod
    def _tool_hint(tool_calls: list) -> str:
        """Format tool calls as concise hint, e.g. 'web_search("query")'."""

        def _fmt(tc):
            args = (tc.arguments[0] if isinstance(tc.arguments, list) else tc.arguments) or {}
            val = next(iter(args.values()), None) if isinstance(args, dict) else None
            if not isinstance(val, str):
                return tc.name
            return f'{tc.name}("{val[:40]}…")' if len(val) > 40 else f'{tc.name}("{val}")'

        return ", ".join(_fmt(tc) for tc in tool_calls)

    @staticmethod
    def _langsmith_enabled() -> bool:
        """Check if LangSmith tracing is enabled in env."""
        if langsmith_trace is None:
            return False
        return os.environ.get("LANGSMITH_TRACING", "").lower() in ("1", "true", "yes")

    @staticmethod
    def _langsmith_project_name() -> str:
        """Resolve LangSmith project name with a stable default."""
        project = os.environ.get("LANGSMITH_PROJECT", "atom-agent")
        if not isinstance(project, str):
            return "atom-agent"
        project = project.strip()
        return project or "atom-agent"

    def _build_langsmith_thread_metadata(
        self,
        *,
        session_key: str,
        project_id: str | None,
    ) -> dict[str, Any]:
        """Build thread metadata for LangSmith spans.

        Session ids are scoped by:
        1) LangSmith project name
        2) Logical project scope (`project_id` or workspace)
        3) Session key (channel/chat pair)
        """
        project_scope = project_id or self.workspace_name
        session_id = f"{self._langsmith_project_name()}:{project_scope}:{session_key}"
        return {
            "session_id": session_id,
            "atom_session_key": session_key,
            "atom_project_scope": project_scope,
        }

    @contextmanager
    def _trace_span(
        self,
        *,
        name: str,
        run_type: str,
        inputs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ):
        """Create a LangSmith trace span if enabled; otherwise no-op context."""
        if not self._langsmith_enabled():
            yield None
            return

        project = self._langsmith_project_name()
        try:
            with langsmith_trace(
                name=name,
                run_type=run_type,
                project_name=project,
                inputs=inputs,
                metadata=metadata,
            ) as span:
                yield span
        except Exception as exc:
            logger.debug("LangSmith tracing skipped", extra={"error": str(exc), "span": name})
            yield None

    async def _run_agent_loop(
        self,
        initial_messages: list[dict],
        on_progress: Callable[..., Awaitable[None]] | None = None,
        trace_metadata: dict[str, Any] | None = None,
    ) -> tuple[str | None, list[str], list[dict]]:
        """Run the agent iteration loop. Returns (final_content, tools_used, messages)."""
        messages = initial_messages
        iteration = 0
        final_content = None
        tools_used: list[str] = []

        while iteration < self.max_iterations:
            iteration += 1

            # Calculate total prompt character count
            prompt_chars = sum(
                len(str(m.get("content", ""))) if m.get("content") else 0 for m in messages
            )

            # Log LLM request with messages and char count
            logger.llm_request(
                model=self.model,
                msg_count=len(messages),
                tools=len(self.tools),
                messages=messages,
                prompt_chars=prompt_chars,
                extra={"iteration": iteration, "workspace": self.workspace_name},
            )
            start_time = time.perf_counter()
            tool_defs = self.tools.get_definitions()
            with self._trace_span(
                name="agent.llm_round",
                run_type="llm",
                inputs={
                    "messages": messages,
                    "tools": tool_defs,
                    "model": self.model,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "reasoning_effort": self.reasoning_effort,
                },
                metadata={
                    **(trace_metadata or {}),
                    "iteration": iteration,
                    "workspace": self.workspace_name,
                },
            ) as llm_span:
                response = await self.provider.chat(
                    messages=messages,
                    tools=tool_defs,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    reasoning_effort=self.reasoning_effort,
                )
                if llm_span is not None:
                    llm_span.add_outputs(
                        {
                            "content": response.content,
                            "finish_reason": response.finish_reason,
                            "usage": response.usage,
                            "tool_calls": [
                                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                                for tc in response.tool_calls
                            ],
                        }
                    )

            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log LLM response with content
            usage = response.usage or {}
            logger.llm_response(
                content_len=len(response.content) if response.content else 0,
                tool_calls=len(response.tool_calls) if response.tool_calls else 0,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                duration_ms=duration_ms,
                content=response.content,
                extra={"finish_reason": response.finish_reason, "iteration": iteration},
            )

            if response.has_tool_calls:
                if on_progress:
                    thought = self._strip_think(response.content)
                    if thought:
                        await on_progress(thought)
                    await on_progress(self._tool_hint(response.tool_calls), tool_hint=True)

                tool_call_dicts = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in response.tool_calls
                ]
                messages = self.context.add_assistant_message(
                    messages,
                    response.content,
                    tool_call_dicts,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )

                for tool_call in response.tool_calls:
                    tools_used.append(tool_call.name)
                    tool_start = time.perf_counter()
                    with self._trace_span(
                        name="agent.tool_call",
                        run_type="tool",
                        inputs={
                            "tool_name": tool_call.name,
                            "arguments": tool_call.arguments,
                            "tool_call_id": tool_call.id,
                        },
                        metadata={
                            **(trace_metadata or {}),
                            "iteration": iteration,
                            "workspace": self.workspace_name,
                        },
                    ) as tool_span:
                        result = await self.tools.execute(tool_call.name, tool_call.arguments)
                        if tool_span is not None:
                            tool_span.add_outputs({"result": result})
                    tool_duration = (time.perf_counter() - tool_start) * 1000
                    logger.tool_call(
                        tool_name=tool_call.name,
                        params=tool_call.arguments,
                        result=result,
                        duration_ms=tool_duration,
                    )
                    messages = self.context.add_tool_result(
                        messages, tool_call.id, tool_call.name, result
                    )
            else:
                clean = self._strip_think(response.content)
                # Don't persist error responses to session history
                if response.finish_reason == "error":
                    final_content = clean or "Sorry, I encountered an error calling the AI model."
                    break
                messages = self.context.add_assistant_message(
                    messages,
                    clean,
                    reasoning_content=response.reasoning_content,
                    thinking_blocks=response.thinking_blocks,
                )
                final_content = clean
                break

        if final_content is None and iteration >= self.max_iterations:
            logger.warning(
                "Max iterations reached",
                extra={"max_iterations": self.max_iterations, "tools_used": len(tools_used)},
            )
            final_content = (
                f"I reached the maximum number of tool call iterations ({self.max_iterations}) "
                "without completing the task. You can try breaking the task into smaller steps."
            )

        return final_content, tools_used, messages

    async def run(self) -> None:
        """Run the agent loop, dispatching messages as tasks to stay responsive to /stop."""
        logger.info(
            "Agent loop starting",
            extra={
                "model": self.model,
                "max_iterations": self.max_iterations,
                "tools": self.tools.tool_names,
                "workspace": self.workspace_name,
            },
        )
        self._running = True
        await self.scheduler.start()
        await self._connect_mcp_tools()

        try:
            while self._running:
                try:
                    msg = await asyncio.wait_for(self.bus.consume_inbound(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue

                if msg.content.strip().lower() == "/stop":
                    await self._handle_stop(msg)
                else:
                    task = asyncio.create_task(self._dispatch(msg))
                    self._active_tasks.setdefault(msg.session_key, []).append(task)
                    task.add_done_callback(
                        lambda t, k=msg.session_key: (
                            self._active_tasks.get(k, []) and self._active_tasks[k].remove(t)
                            if t in self._active_tasks.get(k, [])
                            else None
                        )
                    )
        finally:
            await self._close_mcp_tools()
            await self.scheduler.stop()
            logger.info("Agent loop stopped")

    async def _handle_stop(self, msg: InboundMessage) -> None:
        """Cancel all active tasks for the session."""
        tasks = self._active_tasks.pop(msg.session_key, [])
        cancelled = sum(1 for t in tasks if not t.done() and t.cancel())
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        total = cancelled
        content = f"⏹ Stopped {total} task(s)." if total else "No active task to stop."
        await self.bus.publish_outbound(
            OutboundMessage(channel=msg.channel, chat_id=msg.chat_id, content=content)
        )

    async def _dispatch(self, msg: InboundMessage) -> None:
        """Process a message under the global lock."""
        with trace_context(session_key=msg.session_key):
            logger.user_message(
                content=msg.content,
                channel=msg.channel,
                chat_id=msg.chat_id,
            )
            async with self._processing_lock:
                try:
                    response = await self._process_message(msg)
                    if response is not None:
                        await self.bus.publish_outbound(response)
                    elif msg.channel == "cli":
                        await self.bus.publish_outbound(
                            OutboundMessage(
                                channel=msg.channel,
                                chat_id=msg.chat_id,
                                content="",
                                metadata=msg.metadata or {},
                            )
                        )
                except asyncio.CancelledError:
                    logger.info(
                        "Message processing cancelled", extra={"session_key": msg.session_key}
                    )
                    raise
                except Exception as e:
                    logger.error(
                        "Message processing failed",
                        extra={"error": str(e), "session_key": msg.session_key},
                    )
                    await self.bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content="Sorry, I encountered an error.",
                        )
                    )

    def stop(self) -> None:
        """Stop the agent loop."""
        logger.info("Stop requested")
        self._running = False
        # Best-effort fast shutdown path while run loop exits.
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.scheduler.stop())

    async def _process_message(
        self,
        msg: InboundMessage,
        session_key: str | None = None,
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> OutboundMessage | None:
        """Process a single inbound message and return the response."""
        # Set session key for logging context
        key = session_key or msg.session_key
        set_session_key(key)
        metadata = msg.metadata if isinstance(msg.metadata, dict) else {}
        raw_project_id = metadata.get("project_id")
        project_id = raw_project_id.strip() if isinstance(raw_project_id, str) else None
        if project_id == "":
            project_id = None

        # System messages: parse origin from chat_id ("channel:chat_id")
        if msg.channel == "system":
            channel, chat_id = (
                msg.chat_id.split(":", 1) if ":" in msg.chat_id else ("cli", msg.chat_id)
            )
            key = session_key or msg.session_key_override or f"{channel}:{chat_id}"
            session = self.sessions.get_or_create(key)
            logger.debug(
                "Session loaded",
                extra={"session_key": key, "msg_count": len(session.messages)},
            )
            history = session.get_history(max_messages=self.memory_window)
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content,
                channel=channel,
                chat_id=chat_id,
                project_id=project_id,
            )
            trace_meta = self._build_langsmith_thread_metadata(
                session_key=key,
                project_id=project_id,
            )
            final_content, _, all_msgs = await self._run_agent_loop(
                messages,
                trace_metadata=trace_meta,
            )
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            return OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=final_content or "Background task completed.",
                metadata=msg.metadata or {},
            )

        # Proactive messages
        if msg.channel == "proactive":
            key = session_key or msg.session_key
            session = self.sessions.get_or_create(key)
            logger.debug(
                "Session loaded",
                extra={"session_key": key, "msg_count": len(session.messages), "proactive": True},
            )
            history = session.get_history(max_messages=self.memory_window)
            messages = self.context.build_messages(
                history=history,
                current_message=msg.content,
                channel=msg.channel,
                chat_id=msg.chat_id,
                project_id=project_id,
            )
            trace_meta = self._build_langsmith_thread_metadata(
                session_key=key,
                project_id=project_id,
            )
            final_content, _, all_msgs = await self._run_agent_loop(
                messages,
                trace_metadata=trace_meta,
            )
            self._save_turn(session, all_msgs, 1 + len(history))
            self.sessions.save(session)
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=final_content or "Proactive task completed.",
            )

        key = session_key or msg.session_key
        session = self.sessions.get_or_create(key)
        logger.debug(
            "Session loaded",
            extra={"session_key": key, "msg_count": len(session.messages)},
        )

        # Slash commands
        command_line = msg.content.strip()
        tokens = command_line.split()
        cmd = tokens[0].lower() if tokens else ""

        if cmd == "/new":
            if msg.channel == "feishu" and metadata.get("feishu_new_session"):
                session_id = metadata.get("feishu_session_id", "unknown")
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=f"Started new session: {session_id}",
                    metadata=msg.metadata or {},
                )

            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())
            self._consolidating.add(session.key)
            try:
                async with lock:
                    snapshot = session.messages[session.last_consolidated :]
                    if snapshot:
                        temp = Session(key=session.key)
                        temp.messages = list(snapshot)
                        if not await self._consolidate_memory(temp, archive_all=True):
                            return OutboundMessage(
                                channel=msg.channel,
                                chat_id=msg.chat_id,
                                content="Memory archival failed, session not cleared. Please try again.",
                            )
            except Exception:
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Memory archival failed, session not cleared. Please try again.",
                )
            finally:
                self._consolidating.discard(session.key)

            session.clear()
            self.sessions.save(session)
            self.sessions.invalidate(session.key)
            return OutboundMessage(
                channel=msg.channel, chat_id=msg.chat_id, content="New session started."
            )

        if cmd == "/sessions":
            all_sessions = self.sessions.list_sessions()
            channel_sessions = [
                item
                for item in all_sessions
                if isinstance(item.get("key"), str) and item["key"].startswith(f"{msg.channel}:")
            ]

            active_key = key
            if msg.channel == "feishu":
                chat_id = metadata.get("feishu_chat_id", msg.chat_id)
                active_key = str(metadata.get("feishu_active_session_key", key))
                channel_sessions = [
                    item
                    for item in channel_sessions
                    if item["key"] == f"feishu:{chat_id}"
                    or item["key"].startswith(f"feishu:{chat_id}__")
                    or item["key"] == f"feishu:chitchat:{chat_id}"
                ]

            if not channel_sessions:
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="No sessions found.",
                    metadata=msg.metadata or {},
                )

            lines = ["Sessions:"]
            for item in channel_sessions:
                session_key_text = item.get("key", "")
                if not isinstance(session_key_text, str):
                    continue
                marker = "*" if session_key_text == active_key else " "
                updated = item.get("updated_at", "unknown")
                lines.append(f"{marker} {session_key_text} ({updated})")
            lines.append("* = active session")
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="\n".join(lines),
                metadata=msg.metadata or {},
            )

        if cmd == "/resume":
            if msg.channel == "feishu":
                if metadata.get("feishu_resume_ok"):
                    session_id = metadata.get("feishu_session_id", "unknown")
                    return OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=f"Resumed session: {session_id}",
                        metadata=msg.metadata or {},
                    )
                error_text = metadata.get("feishu_resume_error")
                if isinstance(error_text, str) and error_text:
                    return OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=error_text,
                        metadata=msg.metadata or {},
                    )
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="Usage: /resume <session-id|session-key>",
                metadata=msg.metadata or {},
            )

        if cmd == "/chitchat_on":
            if metadata.get("chitchat_turned_on"):
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Proactive chitchat is now ON.",
                    metadata=msg.metadata or {},
                )
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="Chitchat mode enabled.",
                metadata=msg.metadata or {},
            )

        if cmd in {"/chitchat_off", "/next_time"}:
            if metadata.get("chitchat_ended"):
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content="Proactive chitchat is now OFF.",
                    metadata=msg.metadata or {},
                )
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content="Chitchat mode is already OFF.",
                metadata=msg.metadata or {},
            )

        if cmd == "/help":
            if msg.channel == "feishu":
                return OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=(
                        f"🤖 {self.agent_name} commands:\n"
                        "/new — Start a new session\n"
                        "/sessions — List sessions\n"
                        "/resume <id|key> — Resume session\n"
                        "/chitchat_on — Enable proactive chitchat session\n"
                        "/chitchat_off — Disable proactive chitchat session\n"
                        "/workspace — Show workspace info\n"
                        "/help — Show this help"
                    ),
                    metadata=msg.metadata or {},
                )
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=f"🤖 {self.agent_name} commands:\n/new — Start a new conversation\n/stop — Stop the current task\n/help — Show available commands\n/workspace — Show workspace info",
            )
        if cmd == "/workspace":
            info = self.get_workspace_info()
            return OutboundMessage(
                channel=msg.channel,
                chat_id=msg.chat_id,
                content=(
                    f"📁 Workspace: {info['name']}\n"
                    f"Path: {info['path']}\n"
                    f"Model: {info['model']}\n"
                    f"Sessions: {info['sessions']}\n"
                    f"Skills: {info['skills']['enabled']}/{info['skills']['installed']} enabled\n"
                    f"MCP: {len(info['mcp']['tools'])} tools from {len(info['mcp']['servers'])} server(s)"
                ),
            )
        # Background memory consolidation
        unconsolidated = len(session.messages) - session.last_consolidated
        if unconsolidated >= self.memory_window and session.key not in self._consolidating:
            self._consolidating.add(session.key)
            lock = self._consolidation_locks.setdefault(session.key, asyncio.Lock())

            async def _consolidate_and_unlock():
                try:
                    async with lock:
                        await self._consolidate_memory(session)
                finally:
                    self._consolidating.discard(session.key)
                    _task = asyncio.current_task()
                    if _task is not None:
                        self._consolidation_tasks.discard(_task)

            _task = asyncio.create_task(_consolidate_and_unlock())
            self._consolidation_tasks.add(_task)

        history = session.get_history(max_messages=self.memory_window)
        initial_messages = self.context.build_messages(
            history=history,
            current_message=msg.content,
            media=msg.media if msg.media else None,
            channel=msg.channel,
            chat_id=msg.chat_id,
            project_id=project_id,
        )

        async def _bus_progress(content: str, *, tool_hint: bool = False) -> None:
            meta = dict(msg.metadata or {})
            meta["_progress"] = True
            meta["_tool_hint"] = tool_hint
            await self.bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=content,
                    metadata=meta,
                )
            )

        trace_meta = self._build_langsmith_thread_metadata(
            session_key=key,
            project_id=project_id,
        )
        final_content, _, all_msgs = await self._run_agent_loop(
            initial_messages,
            on_progress=on_progress or _bus_progress,
            trace_metadata=trace_meta,
        )

        if final_content is None:
            final_content = "I've completed processing but have no response to give."

        self._save_turn(session, all_msgs, 1 + len(history))
        self.sessions.save(session)

        return OutboundMessage(
            channel=msg.channel,
            chat_id=msg.chat_id,
            content=final_content,
            metadata=msg.metadata or {},
        )

    def _save_turn(self, session: Session, messages: list[dict], skip: int) -> None:
        """Save new-turn messages into session, truncating large tool results."""
        from datetime import datetime

        for m in messages[skip:]:
            entry = dict(m)
            role, content = entry.get("role"), entry.get("content")
            if role == "assistant" and not content and not entry.get("tool_calls"):
                continue  # skip empty assistant messages
            if (
                role == "tool"
                and isinstance(content, str)
                and len(content) > self._TOOL_RESULT_MAX_CHARS
            ):
                entry["content"] = content[: self._TOOL_RESULT_MAX_CHARS] + "\n... (truncated)"
            elif role == "user":
                if isinstance(content, str) and content.startswith(
                    ContextBuilder._RUNTIME_CONTEXT_TAG
                ):
                    parts = content.split("\n\n", 1)
                    if len(parts) > 1 and parts[1].strip():
                        entry["content"] = parts[1]
                    else:
                        continue
                if isinstance(content, list):
                    filtered = []
                    for c in content:
                        if c.get("type") == "text" and isinstance(c.get("text"), str):
                            if c["text"].startswith(ContextBuilder._RUNTIME_CONTEXT_TAG):
                                continue
                        if c.get("type") == "image_url" and c.get("image_url", {}).get(
                            "url", ""
                        ).startswith("data:image/"):
                            filtered.append({"type": "text", "text": "[image]"})
                        else:
                            filtered.append(c)
                    if not filtered:
                        continue
                    entry["content"] = filtered
            entry.setdefault("timestamp", datetime.now().isoformat())
            session.messages.append(entry)
        session.updated_at = datetime.now()

    async def _consolidate_memory(self, session, archive_all: bool = False) -> bool:
        """Delegate to MemoryStore.consolidate(). Returns True on success."""
        return await MemoryStore(self.workspace).consolidate(
            session,
            self.provider,
            self.model,
            archive_all=archive_all,
            memory_window=self.memory_window,
        )

    async def process_direct(
        self,
        content: str,
        session_key: str = "cli:direct",
        channel: str = "cli",
        chat_id: str = "direct",
        on_progress: Callable[[str], Awaitable[None]] | None = None,
    ) -> str:
        """Process a message directly (for CLI or programmatic usage)."""
        msg = InboundMessage(channel=channel, sender_id="user", chat_id=chat_id, content=content)
        response = await self._process_message(
            msg, session_key=session_key, on_progress=on_progress
        )
        return response.content if response else ""

    async def send_proactive_message(
        self,
        session_key: str,
        content: str,
        channel: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        """
        Send a proactive message to a specific session.

        This allows the agent to initiate communication without waiting for user input.
        """
        # Parse session key to get channel and chat_id if not provided
        if not channel or not chat_id:
            parts = session_key.split(":", 1)
            if len(parts) == 2:
                channel = channel or parts[0]
                chat_id = chat_id or parts[1]
            else:
                channel = channel or "cli"
                chat_id = chat_id or session_key

        await self.bus.publish_outbound(
            OutboundMessage(
                channel=channel,
                chat_id=chat_id,
                content=content,
                metadata={"proactive": True},
            )
        )
