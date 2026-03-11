# AtomAgent IM Channels Integration Findings (Quick Reference)

Date: 2026-03-10
Scope: Feishu / WhatsApp channel integration planning, focused on session/workspace/proactive behavior.
Reference baseline: `reference/nanobot`.

## 1. Current AtomAgent Baseline

1. Session identity is `channel:chat_id` with optional `session_key_override`.
2. Sessions are workspace-local JSONL under `<workspace>/sessions` and include `workspace_name` metadata.
3. Runtime can switch workspace, which rebuilds context and replaces session manager.
4. Proactive config (`PROACTIVE.md`) requires `session_key` in `channel:chat_id` format.
5. Daemon proactive dispatch exists and returns outbound messages, but there is no third-party channel dispatcher in AtomAgent yet.
6. There are two proactive mechanisms today:
   - legacy in-loop `ProactiveScheduler` (message-bus based)
   - file-driven daemon scheduler (`PROACTIVE.md` + `.proactive/state.json`)

## 2. Gap vs Nanobot Gateway Model

1. Nanobot has a full channel runtime:
   - channel adapters (`start/stop/send`)
   - outbound dispatcher (`ChannelManager`)
   - gateway command that runs channels + agent loop together.
2. Nanobot channels already solve platform concerns:
   - ACL (`allow_from`), group policies, dedup, reply/thread metadata, media handling.
3. AtomAgent currently lacks this gateway/channel layer, so proactive output cannot be delivered to IMs end-to-end yet.

## 3. Session Management Findings

1. Keep session key as canonical memory key (stable across inbound/proactive/daemon).
2. Do not over-couple transport routing to session key parsing alone.
3. For group/thread platforms, use `session_key_override` to support richer keys while preserving `chat_id` for delivery.
4. Recommended future-proof rule:
   - `session_key` = conversation memory scope
   - `channel/chat_id/reply/thread metadata` = delivery scope

## 4. Workspace Management Findings

1. AtomAgent’s workspace model is strong and should remain primary isolation boundary.
2. Recommended deployment model for v1:
   - one gateway process == one workspace
   - multi-workspace achieved via multi-process, not one process dynamically routing across workspaces.
3. Reason: avoids accidental context/session bleed and keeps proactive state ownership unambiguous.

## 5. Proactive Feature Findings

1. Existing daemon path is close to usable but currently assumes simple `session_key -> channel/chat_id` splitting.
2. For third-party channels, proactive tasks should support explicit routing fields in addition to `session_key`.
3. Suggested target shape for future config/runtime:
   - `session_key`: memory scope
   - `target.channel`, `target.chat_id`, optional `target.reply_to`/`target.thread_id`
4. The legacy in-loop proactive scheduler should be phased out or disabled in gateway mode to avoid dual scheduling semantics.

## 6. What to Reuse from Nanobot (Directly Useful)

1. `BaseChannel` adapter contract and `ChannelManager` lifecycle.
2. Outbound dispatcher filtering for progress/tool hints.
3. Per-channel session scoping patterns:
   - Slack thread-scoped sessions
   - Telegram topic-scoped sessions.
4. WhatsApp bridge architecture:
   - localhost bind + optional token auth
   - Python adapter over WebSocket.

## 7. Recommended Integration Sequence

1. Add `atom_agent/channels/base.py` + `atom_agent/channels/manager.py`.
2. Add v1 channels: Feishu and WhatsApp.
3. Add `atom-agent gateway run` command (agent loop + channel manager).
4. Add channel config schema (enabled, auth, allow list, policy, progress flags).
5. Route proactive output through channel manager, not CLI-only paths.
6. Unify proactive scheduling path (daemon/file-driven as source of truth).
7. Extend tests for:
   - session-key overrides in channels
   - proactive routing correctness
   - workspace isolation across gateway instances.

## 8. Risks and Design Constraints

1. Duplicate proactive sends if both scheduler paths remain active.
2. Misrouting when deriving delivery target only from session key.
3. Cross-workspace leakage if one process owns multiple workspaces.
4. Channel-specific thread/group semantics causing session fragmentation without clear key rules.

## 9. Open Decisions for Next Discussion

1. Do we commit to one-workspace-per-gateway for v1?
2. Should proactive delivery be final-only by default, or include progress messages?
3. Should proactive tasks fail-fast when target channel is offline, or retry/backoff?
4. Do we add explicit proactive `target` fields now, or after first gateway milestone?

## 10. Proposed Working Defaults

1. Isolation: one workspace per gateway process.
2. Proactive: final-response delivery by default; progress opt-in.
3. Routing: preserve `session_key` for memory, use explicit transport metadata for delivery.
4. Scheduling: daemon/file-driven scheduler as canonical; avoid dual active schedulers.

---
This note is intended as a stable quick reference for future architecture discussions and implementation planning.
