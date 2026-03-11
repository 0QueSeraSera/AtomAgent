# Plan: Standard MCP + Skills Support

Date: 2026-03-11

## Goal
Add generic, standards-aligned support in AtomAgent for:
1. MCP server loading and MCP tool exposure.
2. Skill installation and skill loading from workspace.

No project-specific coupling (including no GitNexus-specific logic) in core implementation.

## Scope Clarification

### Standards to align with
- MCP protocol standard:
  - JSON-RPC based MCP interactions over supported transports.
  - Use MCP SDK semantics for initialize/list_tools/call_tool lifecycle.
- MCP config standard (client-level de facto):
  - Primary config shape: `{ "mcpServers": { ... } }`.
  - Server entry shape: `command`, `args`, `env` (plus transport fields when needed).
- Skills format:
  - Skills are directory-based with canonical `SKILL.md`.
  - Optional local assets/scripts are allowed, but never auto-executed by installer.

### In scope (this iteration)
- Workspace-level MCP config loading and validation.
- MCP stdio transport runtime integration.
- Skill discovery/install/enable/disable in workspace.
- Brief-first skill prompt injection (summary only, not full skill bodies).

### Out of scope (this iteration)
- Any GitNexus-specific built-in skill or hardcoded behavior.
- Hook systems tied to specific clients/editors.
- Auto-running skill scripts during install.
- Non-stdio transports unless required for core correctness.

## Current Gaps
- No MCP runtime/client in AtomAgent.
- No workspace skill discovery or skill installation command.
- No standardized MCP config loading path in workspace.
- No runtime lifecycle hook for MCP tool registration/unregistration.

## Proposed Workspace Contract
```
workspace/
├── .mcp.json                  # MCP config, shape: {"mcpServers": {...}}
├── skills/
│   ├── <skill_name>/
│   │   ├── SKILL.md
│   │   └── ...optional assets/scripts
│   └── manifest.json          # AtomAgent state (enabled/disabled/install source)
```

## Implementation Phases

### Commit 1: Skills Core Loader
- Add `atom_agent/skills/loader.py`:
  - list skills from `workspace/skills/*/SKILL.md`
  - load `SKILL.md` content by name
  - generate brief skills summary for prompt context
- Add `atom_agent/skills/models.py` for metadata + manifest records.
- Inject skill summary into `ContextBuilder` in a bounded section.

Acceptance:
- Agent context contains skills summary when skills exist.
- No full `SKILL.md` dump in system prompt by default.

### Commit 2: Skills Installer + CLI
- Add `atom_agent/skills/installer.py`:
  - install from local path into `workspace/skills/<name>/`
  - validate canonical `SKILL.md` presence
  - update `skills/manifest.json` with enabled state and source
- CLI additions:
  - `atom-agent skill list`
  - `atom-agent skill show <name>`
  - `atom-agent skill install <path>`
  - `atom-agent skill enable|disable <name>`

Acceptance:
- Install/list/show/enable/disable are test-covered and idempotent.

### Commit 3: MCP Config + Client Bridge
- Add `atom_agent/mcp/config.py` and `atom_agent/mcp/models.py`:
  - read `workspace/.mcp.json`
  - validate `mcpServers` schema and normalize values
- Add `atom_agent/mcp/client.py`:
  - connect enabled MCP stdio servers
  - list tools and wrap each as AtomAgent `Tool`
  - wrapper naming: `mcp_<server>_<tool>`
  - tool timeout + robust error handling
- Add `atom_agent/tools/mcp.py` for wrapper implementation.

Acceptance:
- MCP tools are visible in `ToolRegistry` when `.mcp.json` is valid.
- MCP server failure degrades gracefully without crashing agent loop.

### Commit 4: Runtime Lifecycle Integration
- Wire MCP connect/disconnect into `AgentLoop` startup/shutdown.
- Handle workspace switch:
  - close old MCP sessions
  - unregister old MCP tools
  - connect/register for new workspace config
- Ensure CLI chat and gateway runtime share same behavior.

Acceptance:
- No stale MCP tools remain after workspace switch.
- Shutdown leaves no leaked MCP sessions/tasks.

## Testing Plan
- Unit:
  - skills loader + manifest behavior
  - skill installer validation and copy behavior
  - MCP config parsing and schema errors
  - MCP wrapper naming, timeout, error handling
- Integration:
  - context skill summary injection
  - agent startup MCP registration from `.mcp.json`
  - workspace switch lifecycle teardown/reload
- CLI:
  - `skill list/show/install/enable/disable`
  - optional `mcp validate` if included in this iteration

## Risks and Guardrails
- Namespace collisions:
  - enforce `mcp_<server>_<tool>` prefix.
- Prompt bloat:
  - only inject skill summary.
- Security:
  - installer copies files only; never executes skill code.
- Resilience:
  - MCP failures are isolated and non-fatal.
