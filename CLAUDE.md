# CLAUDE.md - Claude Code Instructions for AtomAgent

This file contains project-specific instructions for Claude Code when working on AtomAgent.

## Project Overview

AtomAgent is a Python framework for building proactive, long-running AI agents. See `AGENTS.md` for general coding agent guidelines and `README.md` for user-facing documentation.

## Development Commands

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run linting
ruff check atom_agent/
ruff format atom_agent/

# Run the basic example (requires a real provider implementation)
python examples/basic_agent.py
```

## Architecture Quick Reference

| Component | File | Purpose |
|-----------|------|---------|
| AgentLoop | `atom_agent/agent/loop.py` | Core processing engine |
| ContextBuilder | `atom_agent/agent/context.py` | Builds messages for LLM |
| MessageBus | `atom_agent/bus/queue.py` | Priority message queue |
| MemoryStore | `atom_agent/memory/store.py` | Long-term memory management |
| SessionManager | `atom_agent/session/manager.py` | Conversation persistence |
| ToolRegistry | `atom_agent/tools/registry.py` | Tool registration/execution |

## Coding Standards

- **Line length**: 100 characters max
- **Python version**: 3.11+
- **Style**: Follow ruff rules (E, F, I, W)
- **Async**: All I/O operations should be async

## When Making Changes

1. **Read AGENTS.md first** - it contains essential principles about user experience verification
2. **Check `agent_docs/progress.md`** - see what's in progress
3. **Verify with real execution** - don't rely solely on tests

## Context Files

The `agent_docs/` directory contains coding context that persists across sessions:

- `plan.md` - Current implementation plans
- `progress.md` - Active work tracking
- `archive/` - Completed work
- `notes/` - Technical patterns and gotchas

Update these files as you work to maintain continuity.

## Testing Guidelines

- Write unit tests for isolated component behavior
- For integration testing, prefer real LLM responses over mocks
- Always verify changes work in actual CLI/chat interface

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
