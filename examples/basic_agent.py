"""Example: Basic proactive agent with scheduled tasks."""

import asyncio
from datetime import datetime, timedelta
from pathlib import Path

from atom_agent import (
    AgentLoop,
    MessageBus,
    LLMProvider,
    LLMResponse,
    ToolCallRequest,
    InboundMessage,
    OutboundMessage,
)
from atom_agent.bus.events import ProactiveTask


class MockProvider(LLMProvider):
    """Mock LLM provider for demonstration."""

    def get_default_model(self) -> str:
        return "mock-model"

    async def chat(
        self,
        messages,
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.7,
        reasoning_effort=None,
    ) -> LLMResponse:
        """Simulate LLM responses."""
        last_message = messages[-1].get("content", "")

        # Simple mock responses
        if "hello" in last_message.lower():
            return LLMResponse(content="Hello! I'm your proactive assistant. How can I help?")
        elif "status" in last_message.lower():
            return LLMResponse(content="All systems operational. I'm monitoring for scheduled tasks.")
        else:
            return LLMResponse(content=f"I received your message: {last_message[:100]}")


async def main():
    """Run a basic proactive agent example."""
    # Setup workspace
    workspace = Path("./workspace")
    workspace.mkdir(exist_ok=True)
    (workspace / "memory").mkdir(exist_ok=True)

    # Create message bus and provider
    bus = MessageBus()
    provider = MockProvider(api_key="mock-key")

    # Create agent
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace,
        agent_name="ProactiveBot",
    )

    # Register a proactive task (daily check-in)
    daily_task = ProactiveTask(
        task_id="daily-checkin",
        trigger_type="time",
        trigger_config={"interval_seconds": 60},  # Every minute for demo
        action="Perform daily system check and report status",
        session_key="cli:demo",
    )
    agent.register_proactive_task(daily_task)

    # Start agent in background
    agent_task = asyncio.create_task(agent.run())

    # Simulate user messages
    async def send_message(content: str):
        msg = InboundMessage(
            channel="cli",
            sender_id="user",
            chat_id="demo",
            content=content,
        )
        await bus.publish_inbound(msg)

        # Wait for response
        try:
            response = await asyncio.wait_for(bus.consume_outbound(), timeout=5.0)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Response: {response.content}")
        except asyncio.TimeoutError:
            print("No response received")

    # Send some test messages
    await send_message("Hello!")
    await asyncio.sleep(0.5)

    await send_message("What's your status?")
    await asyncio.sleep(0.5)

    # Stop agent after demo
    await asyncio.sleep(2)
    agent.stop()
    try:
        await asyncio.wait_for(agent_task, timeout=2.0)
    except asyncio.TimeoutError:
        agent_task.cancel()


if __name__ == "__main__":
    print("=== Proactive Agent Demo ===\n")
    asyncio.run(main())
    print("\n=== Demo Complete ===")
