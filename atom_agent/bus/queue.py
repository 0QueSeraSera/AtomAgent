"""Async message queue for decoupled channel-agent communication."""

import asyncio
import heapq
from typing import Any
from datetime import datetime

from atom_agent.bus.events import InboundMessage, OutboundMessage, ProactiveTask


class MessageBus:
    """
    Async message bus that decouples channels from the agent core.

    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.

    Supports priority-based processing for proactive tasks.
    """

    def __init__(self, max_size: int = 0):
        """
        Initialize the message bus.

        Args:
            max_size: Maximum queue size (0 = unlimited).
        """
        self.inbound: asyncio.PriorityQueue[tuple[int, int, InboundMessage]] = asyncio.PriorityQueue(maxsize=max_size)
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue(maxsize=max_size)
        self._counter = 0  # For FIFO ordering within same priority
        self._priority_map = {"high": 0, "normal": 1, "low": 2}

    def _get_priority_value(self, msg: InboundMessage) -> int:
        """Convert priority string to numeric value."""
        return self._priority_map.get(msg.priority, 1)

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent with priority."""
        priority = self._get_priority_value(msg)
        self._counter += 1
        await self.inbound.put((priority, self._counter, msg))

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        priority, counter, msg = await self.inbound.get()
        return msg

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels."""
        await self.outbound.put(msg)

    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()

    def try_consume_outbound(self) -> OutboundMessage | None:
        """Non-blocking consume of outbound message."""
        try:
            return self.outbound.get_nowait()
        except asyncio.QueueEmpty:
            return None

    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()


class ProactiveScheduler:
    """
    Scheduler for proactive tasks.

    Manages time-based, event-based, and condition-based triggers
    for proactive agent behavior.
    """

    def __init__(self, bus: MessageBus):
        self.bus = bus
        self._tasks: dict[str, ProactiveTask] = {}
        self._running = False
        self._scheduler_task: asyncio.Task | None = None

    def register_task(self, task: ProactiveTask) -> None:
        """Register a proactive task."""
        self._tasks[task.task_id] = task

    def unregister_task(self, task_id: str) -> None:
        """Unregister a proactive task."""
        self._tasks.pop(task_id, None)

    def get_task(self, task_id: str) -> ProactiveTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)

    def list_tasks(self, enabled_only: bool = True) -> list[ProactiveTask]:
        """List all registered tasks."""
        tasks = list(self._tasks.values())
        if enabled_only:
            tasks = [t for t in tasks if t.enabled]
        return tasks

    async def start(self) -> None:
        """Start the scheduler loop."""
        self._running = True
        self._scheduler_task = asyncio.create_task(self._run_scheduler())

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

    async def _run_scheduler(self) -> None:
        """Main scheduler loop."""
        while self._running:
            now = datetime.now()
            for task in list(self._tasks.values()):
                if not task.enabled:
                    continue
                if task.next_run and task.next_run <= now:
                    await self._trigger_task(task)
            await asyncio.sleep(1)  # Check every second

    async def _trigger_task(self, task: ProactiveTask) -> None:
        """Trigger a proactive task."""
        task.last_run = datetime.now()
        # Create an inbound message for the agent to process
        msg = InboundMessage(
            channel="proactive",
            sender_id=f"task:{task.task_id}",
            chat_id=task.session_key.split(":")[-1] if ":" in task.session_key else task.session_key,
            content=task.action,
            metadata={"task_id": task.task_id, "trigger_type": task.trigger_type},
            session_key_override=task.session_key,
            priority="high",
        )
        await self.bus.publish_inbound(msg)
