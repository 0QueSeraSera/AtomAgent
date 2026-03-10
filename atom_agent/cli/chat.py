"""Async interactive CLI chat for AtomAgent."""

from __future__ import annotations

import asyncio
import signal
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from atom_agent import AgentLoop, MessageBus
from atom_agent.bus.events import InboundMessage, OutboundMessage
from atom_agent.config import ConfigManager
from atom_agent.logging import get_logger

if TYPE_CHECKING:
    from atom_agent.provider.base import LLMProvider

logger = get_logger("cli.chat")


def _default_workspace_path() -> Path:
    """Resolve default workspace from global registry."""
    return ConfigManager().get_active_workspace_path().expanduser()


class AsyncCLIChat:
    """
    Async interactive CLI chat interface for AtomAgent.

    Features:
    - Real-time user input via async stdin
    - Progress updates during agent thinking
    - Graceful shutdown handling
    - UUID-based session management with /new, /sessions, /resume
    """

    def __init__(
        self,
        provider: LLMProvider,
        workspace: Path | None = None,
        model: str | None = None,
        agent_name: str = "AtomAgent",
        timeout: float = 120.0,
    ):
        self.provider = provider
        self.workspace = workspace or _default_workspace_path()
        self.model = model
        self.agent_name = agent_name
        self.timeout = timeout
        self._current_chat_id = self._new_chat_id()

        self.bus = MessageBus()
        self.agent: AgentLoop | None = None
        self._running = False
        self._agent_task: asyncio.Task | None = None
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._shutdown_event = asyncio.Event()

    @staticmethod
    def _new_chat_id() -> str:
        """Create a UUID session id."""
        return str(uuid.uuid4())

    @property
    def current_session_key(self) -> str:
        """Return current CLI session key."""
        return f"cli:{self._current_chat_id}"

    async def start(self) -> None:
        """Start the CLI chat session."""
        # Ensure workspace has full context (IDENTITY.md, SOUL.md, etc.)
        from atom_agent.cli.management import ensure_workspace_initialized

        self.workspace = self.workspace.expanduser().resolve()
        ensure_workspace_initialized(self.workspace, name="default")

        # Create agent
        self.agent = AgentLoop(
            bus=self.bus,
            provider=self.provider,
            workspace=self.workspace,
            model=self.model,
            agent_name=self.agent_name,
        )

        self._running = True

        # Start agent in background
        self._agent_task = asyncio.create_task(self.agent.run())

        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()

        # Print welcome message
        self._print_welcome()

        # Run the main chat loop
        await self._run_chat_loop()

    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""

        def handle_signal(sig, frame):
            logger.info(f"Received signal {sig}, initiating shutdown...")
            self._shutdown_event.set()

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    def _print_welcome(self) -> None:
        """Print welcome message."""
        print("\n" + "=" * 60)
        print(f"  {self.agent_name} - Interactive CLI Chat")
        print("=" * 60)
        print(f"\nWorkspace: {self.workspace}")
        print(f"Session:   {self._current_chat_id}")
        print("\nType your message and press Enter to chat.")
        print("Type /help to see chat, session, and workspace commands.")
        print("=" * 60 + "\n")

    def _print_help(self) -> None:
        """Print local interface commands."""
        print(
            "\nCommands:\n"
            "  /help                Show this help\n"
            "  /new                 Start a new UUID session\n"
            "  /sessions            List sessions in current workspace\n"
            "  /resume <uuid|key>   Resume a previous session\n"
            "  /workspace           Show current workspace details\n"
            "  /dashboard           Show workspace/session dashboard\n"
            "  /use <workspace>     Switch to a registered workspace\n"
            "  /stop                Stop current task (agent command)\n"
            "  /exit                Exit the chat\n"
        )

    async def _run_chat_loop(self) -> None:
        """Main chat loop handling input and output."""
        # Start input and output handlers concurrently
        input_task = asyncio.create_task(self._handle_input())
        output_task = asyncio.create_task(self._handle_output())

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        # Cancel handlers
        input_task.cancel()
        output_task.cancel()

        # Wait for cancellation
        await asyncio.gather(input_task, output_task, return_exceptions=True)

        # Cleanup
        await self._cleanup()

    async def _handle_input(self) -> None:
        """Handle user input asynchronously."""
        while self._running:
            try:
                # Use asyncio.to_thread for non-blocking input
                user_input = await asyncio.to_thread(self._prompt_input)

                if user_input is None:
                    continue

                user_input = user_input.strip()
                if not user_input:
                    continue

                # Handle local interface commands before sending to agent
                if user_input.startswith("/") and await self._handle_local_command(user_input):
                    continue

                # Send message to agent
                await self._send_message(user_input)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Input error: {e}")
                await asyncio.sleep(0.1)

    async def _handle_local_command(self, raw: str) -> bool:
        """Handle shell-like local commands; return True if handled."""
        tokens = raw.strip().split()
        if not tokens:
            return True

        cmd = tokens[0].lower()

        if cmd == "/exit":
            print("\nGoodbye!")
            self._shutdown_event.set()
            return True

        if cmd == "/help":
            self._print_help()
            return True

        if cmd == "/new":
            self._current_chat_id = self._new_chat_id()
            print(f"Started new session: {self._current_chat_id}")
            return True

        if cmd == "/sessions":
            self._print_sessions()
            return True

        if cmd == "/resume":
            if len(tokens) < 2:
                print("Usage: /resume <uuid|key>")
                return True
            self._resume_session(tokens[1])
            return True

        if cmd in {"/dashboard", "/workspaces"}:
            self._print_dashboard()
            return True

        if cmd == "/workspace":
            self._print_workspace_info()
            return True

        if cmd == "/use":
            if len(tokens) < 2:
                print("Usage: /use <workspace-name>")
                return True
            await self._switch_workspace(tokens[1])
            return True

        return False

    def _print_sessions(self) -> None:
        """List known sessions in current workspace."""
        if self.agent is None:
            print("Session manager not ready yet.")
            return

        sessions = self.agent.sessions.list_sessions()
        if not sessions:
            print("No sessions found in this workspace.")
            return

        print("\nSessions:")
        for session in sessions:
            key = session.get("key", "")
            marker = "*" if key == self.current_session_key else " "
            sid = key.split(":", 1)[1] if ":" in key else key
            updated = session.get("updated_at", "unknown")
            print(f" {marker} {sid}  ({updated})")
        print(" * = current session")

    def _resume_session(self, session_id_or_key: str) -> None:
        """Resume an existing session by uuid or full key."""
        if self.agent is None:
            print("Session manager not ready yet.")
            return

        normalized = (
            session_id_or_key
            if ":" in session_id_or_key
            else f"cli:{session_id_or_key}"
        )
        known_keys = {s.get("key", "") for s in self.agent.sessions.list_sessions()}
        if normalized not in known_keys:
            print(f"Session not found: {session_id_or_key}")
            return

        self._current_chat_id = normalized.split(":", 1)[1] if ":" in normalized else normalized
        print(f"Resumed session: {self._current_chat_id}")

    def _print_dashboard(self) -> None:
        """Show workspace/session dashboard from inside chat."""
        from atom_agent.cli.management import collect_workspace_snapshots, format_workspace_overview

        snapshots = collect_workspace_snapshots(
            ConfigManager(),
            include_paths=[self.workspace],
        )
        print()
        print(format_workspace_overview(snapshots))

    def _print_workspace_info(self) -> None:
        """Show current workspace and session info."""
        print(
            f"Workspace: {self.workspace}\n"
            f"Session:   {self._current_chat_id}\n"
            f"Key:       {self.current_session_key}"
        )

    async def _switch_workspace(self, name: str) -> None:
        """Switch active workspace and agent context."""
        if self.agent is None:
            print("Agent is not ready.")
            return

        config = ConfigManager()
        entry = config.config.workspaces.get(name)
        if not entry:
            print(f"Workspace not found: {name}")
            return
        if not config.set_active_workspace(name):
            print(f"Failed to set active workspace: {name}")
            return

        if not await self.agent.switch_workspace(entry.path, name):
            print(f"Agent failed to switch to workspace: {name}")
            return

        self.workspace = entry.path
        self._current_chat_id = self._new_chat_id()
        print(f"Switched to workspace '{name}' at {entry.path}")
        print(f"Started new session: {self._current_chat_id}")

    def _prompt_input(self) -> str | None:
        """Blocking input prompt (called in thread)."""
        try:
            return input("\n[You]: ")
        except EOFError:
            return "/exit"

    async def _send_message(self, content: str) -> None:
        """Send a message to the agent."""
        msg = InboundMessage(
            channel="cli",
            sender_id="user",
            chat_id=self._current_chat_id,
            content=content,
        )
        await self.bus.publish_inbound(msg)
        print()  # Blank line before response

    async def _handle_output(self) -> None:
        """Handle agent output."""
        while self._running:
            try:
                # Wait for response with timeout
                response = await asyncio.wait_for(
                    self.bus.consume_outbound(),
                    timeout=0.5
                )

                # Format and display response
                self._display_response(response)

            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Output error: {e}")
                await asyncio.sleep(0.1)

    def _display_response(self, response: OutboundMessage) -> None:
        """Format and display agent response."""
        metadata = response.metadata or {}
        session_tag = response.chat_id

        # Handle progress updates
        if metadata.get("_progress"):
            prefix = "  " if metadata.get("_tool_hint") else "[Thinking]: "
            print(f"{prefix}[{session_tag}] {response.content}")
            return

        # Regular response
        if response.content:
            print(f"[{self.agent_name}:{session_tag}] {response.content}")

    async def _cleanup(self) -> None:
        """Cleanup resources."""
        self._running = False

        # Stop agent
        if self.agent:
            self.agent.stop()

        # Wait for agent task to complete
        if self._agent_task:
            try:
                await asyncio.wait_for(self._agent_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._agent_task.cancel()
                try:
                    await self._agent_task
                except asyncio.CancelledError:
                    pass

        # Close provider
        if hasattr(self.provider, "close"):
            await self.provider.close()

        print("\nSession ended.")


async def run_interactive_chat(
    provider: LLMProvider,
    workspace: Path | None = None,
    model: str | None = None,
    agent_name: str = "AtomAgent",
) -> None:
    """
    Convenience function to run an interactive CLI chat.

    Args:
        provider: LLM provider instance
        workspace: Optional workspace directory
        model: Optional model override
        agent_name: Name of the agent
    """
    cli = AsyncCLIChat(
        provider=provider,
        workspace=workspace,
        model=model,
        agent_name=agent_name,
    )
    await cli.start()
