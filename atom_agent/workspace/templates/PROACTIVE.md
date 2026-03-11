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
  "tasks": [
    {
      "id": "self-improve-daily-review",
      "kind": "cron",
      "cron": "0 10 * * *",
      "session_key": "cli:self-improve",
      "enabled": false,
      "metadata": {
        "project_id": "atom-agent-core"
      },
      "prompt": "Run a self-improvement review for project_id=atom-agent-core. Use memory_search to inspect recent project failures/decisions, propose one small coding task, delegate implementation to an external coding assistant in an isolated worktree, verify with tests, and record outcomes back into project memory."
    }
  ]
}
```
