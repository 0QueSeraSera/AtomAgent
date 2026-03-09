# File-Based Context Management Plan

## Overview

This plan outlines the implementation of a file-based context system for AtomAgent, enabling agents to have evolving identities, memories, and behaviors through editable workspace files. The implementation is divided into two major milestones.

## Current State Analysis

### AtomAgent (Current)
- **Context**: Hardcoded in `ContextBuilder._get_identity()` - agent name, guidelines are embedded in code
- **Memory**: Already has `MemoryStore` with `memory/MEMORY.md` and `memory/HISTORY.md`
- **Sessions**: Stored in `workspace/sessions/*.jsonl` - global to workspace
- **Bootstrap Files**: Already loads `AGENTS.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, `IDENTITY.md` from workspace

### Nanobot (Reference)
- **Context**: File-based with workspace loading `BOOTSTRAP_FILES`
- **Skills**: `workspace/skills/{skill-name}/SKILL.md` for extendable capabilities
- **Sessions**: Stored per-workspace at `workspace/sessions/`
- **Memory**: Same two-layer approach (MEMORY.md + HISTORY.md)

### Key Differences
1. AtomAgent lacks a formal skills system
2. AtomAgent's identity is partially hardcoded vs. fully file-based
3. Session management is tied to workspace but identity files are workspace-global

## Proposed Architecture

### Milestone 1: File-Based Context System

Goal: Make agent identity fully configurable through workspace files.

#### Workspace Structure
```
workspace/
├── IDENTITY.md          # Core identity (name, description, personality)
├── SOUL.md              # Values, ethics, behavioral guidelines
├── AGENTS.md            # Technical guidelines for coding/operation
├── USER.md              # User preferences and context
├── TOOLS.md             # Tool usage guidelines
├── memory/
│   ├── MEMORY.md        # Long-term facts (LLM-curated)
│   └── HISTORY.md       # Grep-searchable activity log
└── sessions/            # Session histories
    └── *.jsonl
```

#### Changes Required

1. **ContextBuilder Refactoring** (`atom_agent/agent/context.py`)
   - Remove hardcoded identity from `_get_identity()`
   - Make identity fully derived from `IDENTITY.md`
   - Add fallback template when IDENTITY.md doesn't exist
   - Support runtime metadata injection (time, platform) separately

2. **Workspace Initialization** (`atom_agent/workspace/`)
   - New module for workspace management
   - `WorkspaceManager` class:
     - `init_workspace(path)`: Create default files if missing
     - `validate_workspace(path)`: Check required files exist
     - `get_workspace_config(path)`: Load workspace settings
   - Default template files in `atom_agent/workspace/templates/`

3. **Identity Evolution Support**
   - Agent can modify its own `IDENTITY.md` through file tools
   - Memory consolidation can suggest identity updates
   - Track identity changes in HISTORY.md

4. **CLI Commands** (new in `atom_agent/cli/`)
   - `atom-agent init [path]`: Initialize a new workspace
   - `atom-agent identity show`: Display current identity
   - `atom-agent workspace validate`: Check workspace health

#### Implementation Steps

1. Create `atom_agent/workspace/__init__.py`
2. Create `atom_agent/workspace/manager.py` with `WorkspaceManager`
3. Create `atom_agent/workspace/templates/` with default files
4. Refactor `ContextBuilder` to use file-based identity
5. Add CLI commands for workspace management
6. Add tests for workspace initialization
7. Update documentation

### Milestone 2: Session & Workspace Management

Goal: Link sessions to agent identity, support multiple workspaces and session switching.

#### Enhanced Workspace Structure
```
~/.atomagent/
├── workspaces/
│   ├── default/
│   │   ├── IDENTITY.md
│   │   ├── SOUL.md
│   │   ├── memory/
│   │   │   ├── MEMORY.md
│   │   │   └── HISTORY.md
│   │   └── sessions/
│   │       ├── cli_direct.jsonl
│   │       └── telegram_12345.jsonl
│   ├── work-assistant/
│   │   ├── IDENTITY.md (work-focused)
│   │   └── sessions/
│   └── personal-assistant/
│       ├── IDENTITY.md (personal-focused)
│       └── sessions/
├── config.yaml           # Global configuration
└── current_workspace -> workspaces/default/  # Symlink or config
```

#### Changes Required

1. **Workspace Registry** (`atom_agent/workspace/registry.py`)
   - `WorkspaceRegistry` class:
     - `list_workspaces()`: List all known workspaces
     - `get_workspace(name)`: Get workspace by name
     - `create_workspace(name, template)`: Create new workspace
     - `delete_workspace(name)`: Remove workspace
     - `get_active_workspace()`: Get current active workspace
     - `set_active_workspace(name)`: Switch active workspace

2. **Session Management Refactoring** (`atom_agent/session/manager.py`)
   - Sessions belong to specific workspaces
   - `SessionManager` takes workspace path, not arbitrary path
   - Support session metadata for workspace association
   - Add session import/export between workspaces

3. **AgentLoop Updates** (`atom_agent/agent/loop.py`)
   - Support workspace switching at runtime
   - Maintain session continuity across workspace switches
   - Handle workspace-specific tool configurations

4. **Configuration System** (`atom_agent/config/`)
   - New config module for global settings
   - `config.yaml` schema:
     ```yaml
     active_workspace: default
     default_provider: anthropic
     workspaces:
       default:
         path: ~/.atomagent/workspaces/default
       work-assistant:
         path: ~/.atomagent/workspaces/work-assistant
     ```
   - Environment variable overrides (`ATOMAGENT_WORKSPACE`, etc.)

5. **CLI Commands** (extended)
   - `atom-agent workspace list`: List all workspaces
   - `atom-agent workspace switch <name>`: Switch active workspace
   - `atom-agent workspace create <name>`: Create new workspace
   - `atom-agent session list`: List sessions in current workspace
   - `atom-agent session export <key>`: Export session
   - `atom-agent session import <file>`: Import session to workspace

6. **API for Multi-Workspace**
   - Programmatic workspace switching
   - Workspace-aware tool registration
   - Per-workspace tool configurations

#### Implementation Steps

1. Create `atom_agent/config/__init__.py` and schema
2. Create `atom_agent/workspace/registry.py`
3. Refactor `SessionManager` for workspace association
4. Update `AgentLoop` for workspace awareness
5. Add workspace CLI commands
6. Add session management CLI commands
7. Add configuration file support
8. Add migration tool for existing workspaces
9. Update documentation

## File Templates

### IDENTITY.md (Default)
```markdown
# AtomAgent

You are AtomAgent, a proactive AI assistant capable of long-running tasks and autonomous operation.

## Core Traits
- Helpful and responsive
- Thorough in task completion
- Proactive in communication
- Adaptable to user preferences

## Capabilities
- Long-running task execution
- Autonomous operation with user oversight
- Memory and context retention across sessions
- Multi-channel communication

## Behavioral Guidelines
- State intent before taking action
- Verify assumptions before proceeding
- Communicate progress on long tasks
- Ask for clarification when uncertain
```

### SOUL.md (Template)
```markdown
# Core Values

## Ethics
- Respect user privacy and data
- Be honest about capabilities and limitations
- Prioritize user safety and wellbeing

## Communication Style
- Clear and concise
- Appropriate level of detail
- Proactive updates on progress

## Learning
- Remember user preferences
- Improve based on feedback
- Maintain consistency with established patterns
```

## Migration Strategy

### From Current AtomAgent
1. Auto-detect existing workspace structure
2. Create `IDENTITY.md` from current hardcoded identity
3. Preserve existing `memory/` and `sessions/` directories
4. No breaking changes to existing code paths

### Backward Compatibility
- `ContextBuilder(workspace)` continues to work
- Default identity used when `IDENTITY.md` missing
- Existing session files remain valid

## Testing Strategy

1. **Unit Tests**
   - Workspace initialization
   - File loading and parsing
   - Identity resolution
   - Configuration management

2. **Integration Tests**
   - Full agent loop with file-based context
   - Workspace switching
   - Session persistence across workspaces

3. **E2E Tests**
   - CLI commands
   - Multi-workspace scenarios

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Breaking existing users | Backward compatible defaults |
| File corruption | Backup before writes, validation |
| Performance impact | Lazy loading, caching |
| Complex workspace management | Clear CLI, good defaults |

## Timeline Estimate

- **Milestone 1**: ~3-4 days
  - Workspace manager: 1 day
  - ContextBuilder refactor: 1 day
  - CLI commands: 0.5 day
  - Testing: 1 day

- **Milestone 2**: ~4-5 days
  - Config system: 1 day
  - Workspace registry: 1 day
  - Session refactoring: 1 day
  - CLI commands: 1 day
  - Testing: 1 day

## Dependencies

- No new external dependencies required
- Uses existing `pathlib`, `pydantic` (if available)
- Optional: `rich` for enhanced CLI output

## Open Questions

1. Should workspaces support inheritance (e.g., work-assistant extends default)?
2. How to handle workspace switching during active sessions?
3. Should there be a "global" memory that spans workspaces?
4. How to sync workspaces across machines (if at all)?

## References

- Nanobot workspace implementation: `/Users/alive/workspace/OSS_contribute/nanobot`
- Current AtomAgent context: `atom_agent/agent/context.py`
- Current AtomAgent memory: `atom_agent/memory/store.py`
