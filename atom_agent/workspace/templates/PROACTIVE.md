# Proactive Configuration

Use the JSON block below to define proactive tasks.
Keep this file human-readable, but maintain exactly one valid JSON code block.

Task routing notes:
- `session_key` controls memory/session scope.
- Optional `target` controls transport delivery scope:
  - `target.channel`
  - `target.chat_id`
  - optional `target.reply_to`
  - optional `target.thread_id`

```json
{
  "version": 1,
  "enabled": false,
  "timezone": "UTC",
  "tasks": []
}
```
