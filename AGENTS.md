# Coding Agent Guidelines for AtomAgent

This document provides guidance for AI coding agents (Codex, Claude Code, etc.) working on the AtomAgent project.

## Core Principles

### 1. User Experience First

- **Verify features work in real interfaces**, not just in tests. A CLI chat, API endpoint, or UI interaction must actually work as expected.
- **Run the actual application** to confirm changes take effect. Do not rely solely on unit tests or syntax checks.
- **Test end-to-end flows** when modifying core agent behavior (message processing, tool execution, memory consolidation).

### 2. Real Runtime Verification

- **Use real LLM responses** when verifying agent behavior. No stubs, no mocks for integration testing.
- **Refer to actual runtime logs** to verify the project's LLM behaves as expected.
- **Check real outputs** from the agent loop, tool executions, and memory operations.
- When in doubt, run `examples/basic_agent.py` or create a minimal reproduction script.

### 3. Context Management via `agent_docs/`

The `agent_docs/` directory is the source of truth for coding context:

```
agent_docs/
├── plan.md        # Current implementation plan and architecture decisions
├── progress.md    # Active work items, in-progress tasks, blockers
├── archive/       # Completed tasks and deprecated plans
└── notes/         # Technical notes, patterns, and gotchas
```

**Agents should:**
- Read `agent_docs/plan.md` before starting work to understand current direction
- Update `agent_docs/progress.md` with task status and findings
- Move completed items to `agent_docs/archive/` with timestamps
- Document non-obvious patterns in `agent_docs/notes/`

## Project Architecture

AtomAgent is a Python framework for building proactive, long-running AI agents.

```
atom_agent/
├── agent/         # Core agent loop and context building
│   ├── loop.py    # Main AgentLoop class - message processing engine
│   └── context.py # ContextBuilder - system prompts and message assembly
├── bus/           # Message bus for channel communication
│   ├── events.py  # InboundMessage, OutboundMessage, ProactiveTask
│   └── queue.py   # MessageBus (priority queue) and ProactiveScheduler
├── memory/        # Long-term memory system
│   └── store.py   # MemoryStore - MEMORY.md and HISTORY.md management
├── provider/      # LLM provider interface
│   └── base.py    # Abstract LLMProvider class and data types
├── session/       # Session management
│   └── manager.py # Session and SessionManager classes
└── tools/         # Tool system
    ├── base.py    # Abstract Tool class
    ├── registry.py# ToolRegistry - registration and execution
    └── message.py # MessageTool for proactive messaging
```

## Git Worktree Development Pattern

Agents MUST use git worktrees for isolated development when working on features or bug fixes.
This ensures the main repository remains stable and allows parallel development.

### Worktree Naming Convention

```
atomAgent-worktree-{type}-{description}
```

- **type**: `fix`, `feat`, `perf`, `refactor`, `docs`, `test`, `chore`
- **description**: short kebab-case description of the work

Examples:
- `atomAgent-worktree-fix-login-timeout`
- `atomAgent-worktree-feat-openai-provider`
- `atomAgent-worktree-perf-context-building`

### Branch Naming Convention

Branches follow the same prefix pattern:

```
{type}/{description}
```

Examples:
- `fix/login-timeout`
- `feat/openai-provider`
- `perf/context-building`

### Worktree Rules

**CRITICAL: Agents working within a git worktree are NOT allowed to:**
- Manipulate the main repository (`main` branch)
- Push to or modify other agents' branches
- Create or delete branches in the main repo
- Merge branches or perform operations affecting the main repo

**Agents CAN:**
- Commit to their own worktree's branch
- Push their own branch to remote
- Create commits and update their worktree's branch

### Creating a Worktree

```bash
# Create a worktree with a new branch
git worktree add ../atomAgent-worktree-feat-my-feature -b feat/my-feature

# Or from an existing branch
git worktree add ../atomAgent-worktree-fix-bug -b fix/bug-name origin/main
```

### Worktree Workflow

1. **Create worktree** for your task with appropriate naming
2. **Do your work** in the worktree directory
3. **Commit and push** only to your branch
4. **Create PR** when ready for review
5. **Clean up** worktree after merge:
   ```bash
   git worktree remove ../atomAgent-worktree-feat-my-feature
   ```

### Listing and Managing Worktrees

```bash
# List all worktrees
git worktree list

# Remove a worktree (after work is complete)
git worktree remove <path>

# Prune stale worktree references
git worktree prune
```

## Development Workflow

### Before Making Changes

1. Read `agent_docs/plan.md` and `agent_docs/progress.md`
2. Understand the existing code by reading relevant source files
3. Identify affected components and their dependencies
4. **Create a git worktree** for isolated development

### After Making Changes

1. **Run the actual code** - verify with real LLM calls, not just pytest
2. Update `agent_docs/progress.md` with what was done
3. Archive completed work to `agent_docs/archive/`

### Testing Philosophy

- Unit tests are for isolated component behavior
- Integration tests should use real LLM responses when feasible
- Always verify CLI/chat interface works after changes

## Key Patterns

### Agent Loop Flow

```
InboundMessage → Context Build → LLM Call → Tool Execution → OutboundMessage
                     ↑                                    ↓
              Session History ←─────────────────────── Save Turn
```

### Memory Consolidation

When conversation history exceeds `memory_window`, background consolidation:
1. Extracts important facts → `MEMORY.md`
2. Archives conversation → `HISTORY.md`
3. Clears session history

### Tool Registration

Tools extend the `Tool` base class and are registered via `agent.register_tool()`.

## Python Environment Setup

**CRITICAL: Always use a virtual environment. NEVER install packages to system Python.**

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -e ".[dev]"
```

Before running any commands, ensure your virtual environment is active. You should see `(.venv)` in your terminal prompt.

## Commands

```bash
# Run tests
pytest tests/

# Run example (requires implementing a real provider)
python examples/basic_agent.py

# Lint
ruff check atom_agent/
```

## Important Notes

- **Virtual environment is mandatory** - never install to system Python
- Python 3.11+ required
- Uses asyncio throughout
- No external LLM SDK dependencies (providers implement their own)
- Session keys format: `{channel}:{chat_id}`
