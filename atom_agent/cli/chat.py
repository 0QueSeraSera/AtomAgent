"""Async interactive CLI chat for AtomAgent."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from atom_agent import AgentLoop, MessageBus
from atom_agent.bus.events import InboundMessage, OutboundMessage

if TYPE_CHECKING:
    from atom_agent.provider.base import LLMProvider

logger = logging.getLogger(__name__)


class AsyncCLIChat:
    """
    Async interactive CLI chat interface for AtomAgent.

    Features:
    - Real-time user input via async stdin
    - Progress updates during agent thinking
    - Graceful shutdown handling
    - Session management with /new, /help, /exit commands
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
        self.workspace = workspace or Path("./workspace")
        self.model = model
        self.agent_name = agent_name
        self.timeout = timeout

        self.bus = MessageBus()
        self.agent: AgentLoop | None = None
        self._running = False
        self._agent_task: asyncio.Task | None = None
        self._input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the CLI chat session."""
        # Setup workspace
        self.workspace.mkdir(exist_ok=True)
        (self.workspace / "memory").mkdir(exist_ok=True)

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
        print("\nCommands:")
        print("  /help   - Show available commands")
        print("  /new    - Start a new conversation")
        print("  /exit   - Exit the chat")
        print("  /stop   - Stop current task")
        print("\nType your message and press Enter to chat.")
        print("=" * 60 + "\n")

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

                # Handle exit command
                if user_input.lower() == "/exit":
                    print("\nGoodbye!")
                    self._shutdown_event.set()
                    break

                # Send message to agent
                await self._send_message(user_input)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Input error: {e}")
                await asyncio.sleep(0.1)

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
            chat_id="interactive",
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

        # Handle progress updates
        if metadata.get("_progress"):
            prefix = "  " if metadata.get("_tool_hint") else "[Thinking]: "
            print(f"{prefix}{response.content}")
            return

        # Regular response
        if response.content:
            print(f"[{self.agent_name}]: {response.content}")

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
