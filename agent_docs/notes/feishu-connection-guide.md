# Feishu Connection Guide (Gateway v1)

Date: 2026-03-10
Scope: `atom-agent gateway run` + `atom_agent.channels.feishu.FeishuAdapter`

## 1. Feishu Open Platform Setup

1. Create an app at `https://open.feishu.cn/app`.
2. Enable bot capability.
3. Enable event subscriptions for message receive events.
4. Copy app credentials:
   - `App ID`
   - `App Secret`
5. (Optional but recommended) configure webhook verification token.

## 2. Required Runtime Config

Set environment variables before starting gateway:

```bash
export DEEPSEEK_API_KEY=...
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx
export FEISHU_VERIFICATION_TOKEN=optional_token
```

Optional controls:

```bash
export FEISHU_ALLOW_USER_IDS=ou_xxx,ou_yyy
export FEISHU_ALLOW_GROUP_CHATS=true
export FEISHU_DEDUP_CACHE_SIZE=1024
```

## 3. Start Gateway

Readiness check only:

```bash
atom-agent gateway run --once --workspace /path/to/workspace
```

Long-running gateway:

```bash
atom-agent gateway run --workspace /path/to/workspace
```

## 4. Webhook Event Handling

`FeishuAdapter` exposes `handle_webhook_event(payload, headers=...)` so an external HTTP endpoint can forward raw Feishu callback payloads into AtomAgent:

1. Validate incoming request in your HTTP framework.
2. Parse JSON payload.
3. Call `await feishu_adapter.handle_webhook_event(payload, headers=request.headers)`.
4. Return the adapter result as JSON.

`handle_webhook_event` supports:
- challenge response (`{"challenge": ...}`)
- verification token check when configured
- dedup by event/message id
- message mapping into `InboundMessage(channel="feishu", ...)`

## 5. Troubleshooting

1. `Feishu adapter is not ready`: missing `FEISHU_APP_ID` or `FEISHU_APP_SECRET`.
2. `verification token mismatch`: callback token does not match configured value.
3. No responses in group chats: verify `FEISHU_ALLOW_GROUP_CHATS=true` or pass `--feishu-deny-group` intentionally.
4. Repeated duplicate events: expected on Feishu retries; adapter dedup cache suppresses replay.
