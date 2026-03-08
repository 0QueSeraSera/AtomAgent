# CLAUDE.md - Claude Code Instructions for AtomAgent

This file contains project-specific instructions for Claude Code when working on AtomAgent.

## Project Overview

AtomAgent is a Python framework for building proactive, long-running AI agents. See `AGENTS.md` for general coding agent guidelines and `README.md` for user-facing documentation.

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
3. **Create a git worktree** - use isolated worktrees for development (see below)
4. **Verify with real execution** - don't rely solely on tests

## Git Worktree Development

Claude Code should use git worktrees for isolated development. This prevents conflicts and keeps
the main repository stable.

### Quick Reference

| Task Type | Worktree Name | Branch Name |
|-----------|---------------|-------------|
| Bug fix | `atomAgent-worktree-fix-{desc}` | `fix/{desc}` |
| Feature | `atomAgent-worktree-feat-{desc}` | `feat/{desc}` |
| Performance | `atomAgent-worktree-perf-{desc}` | `perf/{desc}` |
| Refactor | `atomAgent-worktree-refactor-{desc}` | `refactor/{desc}` |
| Docs | `atomAgent-worktree-docs-{desc}` | `docs/{desc}` |

### Creating a Worktree

```bash
# Create worktree with new branch from main
git worktree add ../atomAgent-worktree-feat-new-provider -b feat/new-provider

# Work in the worktree
cd ../atomAgent-worktree-feat-new-provider
# ... make changes, commit, push ...
```

### Worktree Constraints

**When working in a worktree, you MUST NOT:**
- Modify the `main` branch directly
- Push to other branches or worktrees
- Perform operations on the main repository

**You MAY:**
- Commit to your worktree's branch
- Push your branch to remote
- Create PRs from your branch

### Cleanup After Merge

```bash
# Remove worktree after PR is merged
git worktree remove ../atomAgent-worktree-feat-new-provider
```

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
