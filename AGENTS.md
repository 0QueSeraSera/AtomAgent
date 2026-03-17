# AGENTS.md - Coding Agents (Codex, Cursor, Claude Code, etc.) Instructions for AtomAgent

This file contains project-specific instructions for AI coding agents when working on AtomAgent.

## Project Overview

AtomAgent is a Python framework for building **proactive, long-running AI agents**. Unlike traditional chatbots that only respond to user messages, AtomAgent agents can:

- **Initiate conversations** autonomously (proactive messaging)
- **Schedule tasks** to run at specific times or intervals
- **Maintain persistent memory** across sessions
- **Integrate with multiple channels** (CLI, Feishu/Lark)

See `AGENTS.md` for general coding agent guidelines and `README.md` for user-facing documentation.

## Core Features

### Proactive Agent System
Agents can send messages without waiting for user input via:
- **ProactiveTask**: Time-based or event-based scheduled tasks
- **ProactiveScheduler**: Manages task execution and state
- **Chitchat**: Auto-generated casual messages for engagement

### Multi-Channel Support
- **CLI**: Interactive terminal-based chat
- **Feishu/Lark**: Enterprise messaging with WebSocket long-connection or webhook modes
- **Session routing**: Per-user/per-thread session isolation

### Memory System
Two-layer memory architecture:
- **MEMORY.md**: Long-term facts about the user and context
- **HISTORY.md**: Searchable conversation log with consolidation

## Development Commands

**IMPORTANT: Always use a virtual environment. Never install to system Python.**

```bash
# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run specific test file
pytest tests/test_agent_loop.py -v

# Run linting
ruff check atom_agent/
ruff format atom_agent/

# Run the basic example (requires a real provider implementation)
python examples/basic_agent.py

# Run gateway mode with Feishu
atom-agent gateway run --workspace ./workspace
```

## Coding Standards

- **Line length**: 100 characters max
- **Python version**: 3.11+
- **Style**: Follow ruff rules (E, F, I, W)
- **Async**: All I/O operations should be async
- **Type hints**: Use type annotations for function signatures
- **Docstrings**: Use for public APIs, not for trivial functions

## Architecture Principles

### Async-First Design
All I/O operations are async. The agent runs in an async event loop and channels, providers, and tools should use async/await.

### Channel Isolation
Each channel (CLI, Feishu) has its own adapter but shares the core AgentLoop. Session keys uniquely identify conversations (e.g., `feishu:user_123`).

### Tool System
Tools are self-contained units with:
- JSON schema for parameters
- Async execute method
- Automatic registration via ToolRegistry

### Provider Abstraction
LLM providers implement a common interface (`LLMProvider`), making it easy to swap models (DeepSeek, OpenAI, Anthropic, etc.).

## Key Files to Understand

| Area | Key Files | Purpose |
|------|-----------|---------|
| Core Loop | `agent/loop.py` | Main agent processing engine |
| Context | `agent/context.py` | Builds system prompts and messages for LLM |
| Message Bus | `bus/queue.py` | Priority queue for incoming messages |
| Proactive | `proactive/runtime.py`, `proactive/scheduler.py` | Task scheduling and execution |
| Channels | `channels/feishu.py`, `channels/manager.py` | External channel integrations |
| Memory | `memory/store.py` | Long-term memory management |
| CLI | `cli/__main__.py` | Entry point for all CLI commands |

## When Making Changes

1. **Read AGENTS.md first** - it contains essential principles about user experience verification
2. **Check `agent_docs/progress.md`** - see what's in progress
4. **Verify with real execution** - don't rely solely on tests

## Context Files

The `agent_docs/` directory contains coding context that persists across sessions:

- `plan.md` - Current implementation plans
- `progress.md` - Active work tracking
- `archived/` - Completed work
- `notes/` - Technical patterns and gotchas

Update these files as you work to maintain continuity.

## Testing Guidelines

- Write unit tests for isolated component behavior
- For integration testing, prefer real LLM responses over mocks
- Always verify changes work in actual CLI/chat interface
- Test files follow pattern: `test_{module}_{feature}.py`
- E2E tests are prefixed with `e2e_`

## Common Tasks

### Adding a New Tool

1. Extend `Tool` class from `atom_agent/tools/base.py`
2. Implement `name`, `description`, `parameters`, and `execute()`
3. Register with `agent.register_tool(MyTool())`

### Adding a New Provider

1. Extend `LLMProvider` from `atom_agent/provider/base.py`
2. Implement `get_default_model()` and `chat()`
3. Return `LLMResponse` objects

### Modifying Agent Behavior

The main loop is in `atom_agent/agent/loop.py`. Key methods:
- `run()` - Main event loop
- `_process_message()` - Handle single message
- `_run_agent_loop()` - Iteration loop with tool calls

## Environment Variables

Key configuration via environment variables:

| Variable | Purpose |
|----------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek LLM API key |
| `FEISHU_APP_ID` | Feishu app ID |
| `FEISHU_APP_SECRET` | Feishu app secret |
| `ATOM_AGENT_WORKSPACE` | Default workspace directory |

See `.env.example` for full list.
