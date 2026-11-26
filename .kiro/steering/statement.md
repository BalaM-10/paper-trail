# Statement

Before reporting task completion, write `.papertrail/statement.json` with exactly this schema (no other fields):

```json
{
  "summary": "<one sentence ending with a period>",
  "files_read":     ["<relative/forward/slash/path>"],
  "files_created":  ["<relative/forward/slash/path>"],
  "files_modified": ["<relative/forward/slash/path>"],
  "files_deleted":  ["<relative/forward/slash/path>"]
}
```

Constraints:
- All paths must be relative and use forward slashes (`/`), never back-slashes or drive letters.
- `summary` must be a single sentence with no newlines, ending with `.`.
- Each list may be empty (`[]`).
- No duplicate paths within a list.
- Do not include `session_id`, `ts`, or `witness_seq` — the stop hook adds those.

## When this applies

This rule is mandatory. It applies to every reply in which you created,
changed or deleted any file, or ran any shell command, however small the task.
Writing `.papertrail/statement.json` must be your last tool call before your
final message. List only what you know you did. Do not inspect the folder to
find out what changed; report from your own actions and the output you saw.
