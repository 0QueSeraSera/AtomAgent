# AtomAgent

A Python framework for building proactive, long-running AI agents.

## Features

- **Proactive Communication**: Agents can initiate messages without waiting for user input
- **Long-Running Tasks**: Built-in support for extended operations with proper session management
- **Memory System**: Two-layer memory (long-term facts + searchable history)
- **Priority Message Processing**: Messages are processed by priority (high/normal/low)
- **Scheduled Tasks**: Proactive task scheduler for time-based and event-based triggers
- **Tool System**: Extensible tool registry with JSON schema validation
- **Session Management**: Persistent conversation history with automatic consolidation

## Installation

```bash
pip install atom-agent
```

## Quick Start

```python
import asyncio
from pathlib import Path
from atom_agent import (
    AgentLoop,
    MessageBus,
    LLMProvider,
    LLMResponse,
    ToolCallRequest,
)

# Implement a custom LLM provider
class MyProvider(LLMProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key=api_key)

    def get_default_model(self) -> str:
        return "gpt-4"

    async def chat(
        self,
        messages,
        tools=None,
        model=None,
        max_tokens=4096,
        temperature=0.7,
        reasoning_effort=None,
    ) -> LLMResponse:
        # Implement your LLM API call here
        # This is a placeholder
        return LLMResponse(content="Hello! How can I help you?")

async def main():
    # Create workspace
    workspace = Path("./workspace")
    workspace.mkdir(exist_ok=True)

    # Initialize components
    bus = MessageBus()
    provider = MyProvider(api_key="your-api-key")
    agent = AgentLoop(
        bus=bus,
        provider=provider,
        workspace=workspace,
    )

    # Run the agent
    await agent.run()

if __name__ == "__main__":
    asyncio.run(main())
```

## Architecture

```
atom_agent/
├── agent/           # Core agent loop and context builder
│   ├── loop.py      # Main agent processing engine
│   └── context.py   # System prompt and message building
├── bus/             # Message bus for channel communication
│   ├── events.py    # InboundMessage, OutboundMessage, ProactiveTask
│   └── queue.py     # Priority queue and proactive scheduler
├── memory/          # Long-term memory system
│   └── store.py     # MEMORY.md + HISTORY.md management
├── provider/        # LLM provider interface
│   └── base.py      # Abstract provider class
├── session/         # Session management
│   └── manager.py   # Conversation persistence
└── tools/           # Tool system
    ├── base.py      # Abstract tool class
    ├── registry.py  # Tool registration and execution
    └── message.py   # Proactive messaging tool
```

## Key Concepts

### Proactive Tasks

Agents can schedule tasks to run autonomously:

```python
from atom_agent.bus.events import ProactiveTask
from datetime import datetime, timedelta

# Schedule a daily summary
task = ProactiveTask(
    task_id="daily-summary",
    trigger_type="time",
    trigger_config={"schedule": "0 9 * * *"},  # 9 AM daily
    action="Generate a summary of today's activities",
    session_key="telegram:user123",
)

agent.register_proactive_task(task)
```

### Custom Tools

Create custom tools by extending the `Tool` class:

```python
from atom_agent.tools.base import Tool

class WeatherTool(Tool):
    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "Get current weather for a location"

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City name"
                }
            },
            "required": ["location"]
        }

    async def execute(self, location: str) -> str:
        # Implement weather lookup
        return f"Weather in {location}: Sunny, 25°C"

# Register the tool
agent.register_tool(WeatherTool())
```

### Memory Management

The agent maintains long-term memory automatically:

- `MEMORY.md`: Important facts and information
- `HISTORY.md`: Searchable log of conversations

Memory is consolidated when conversations exceed the memory window.

## License

MIT
