# Active Progress

Date: 2026-03-14
Branch: `fix/proactive-chitchat-switch`

## Refactor: Feishu Proactive Chitchat Switch Decoupled from Routing

Status: In progress (proactive switch split landed, validation complete)

### Completed

1. Refactored Feishu session router into persisted command-aware state machine:
   - multi normal sessions per chat (`/new`, `/resume`, `/sessions` metadata support)
   - dedicated chitchat session scope
   - command aliases (`/next_time` -> `/chitchat_off`)
   - persisted state in workspace (`.feishu_sessions.json`)
2. Added persisted per-chat `proactive_chitchat_enabled` flag in Feishu router.
3. Added explicit proactive toggle commands:
   - `/proactive_chitchat_on`
   - `/proactive_chitchat_off`
4. Kept `/chitchat_on|off` focused on manual inbound routing into/out of chitchat session history.
5. Updated Feishu adapter proactive suppression logic to use proactive switch (not routing mode).
6. Updated proactive session resolver to allow dedicated chitchat memory routing when proactive switch is ON.
7. Updated agent command responses/help text to separate routing commands from proactive-start commands.
8. Extended router/channel/gateway tests for new semantics.

### Validation

1. `../../.venv/bin/python -m pytest -q tests/test_feishu_session_router.py tests/test_channels_feishu.py tests/test_gateway_runtime.py`
   - Result: 20 passed
2. `../../.venv/bin/python -m ruff check atom_agent/channels/feishu.py atom_agent/channels/feishu_session.py atom_agent/agent/loop.py tests/test_feishu_session_router.py tests/test_channels_feishu.py tests/test_gateway_runtime.py`
   - Result: all checks passed
3. `PYTHONPATH=. ../../.venv/bin/python -m atom_agent --help | sed -n '1,140p'`
   - Result: CLI command surface loads successfully in this worktree.

### Notes

1. Local environment has real Feishu credentials/.env values, so `tests/test_cli_gateway.py::test_gateway_once_fails_without_feishu_credentials` is environment-sensitive in this shell and not used as refactor gate.
