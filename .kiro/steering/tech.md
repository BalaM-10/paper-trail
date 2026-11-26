# Technology

## Stack
- Python 3.11 for the recorder, witness, verifier, API and MCP server.
- FastAPI for the local API.
- React with TypeScript and Vite for the printout view.
- Storage is plain files. No database.
- Tests: pytest, with Hypothesis property-based tests for the hash chain and
  the verifier.

## Environment
- Development machine is Windows. Kiro runs shell commands in PowerShell.
- Hook commands must start with `python` and must not rely on bash, PowerShell
  syntax, or the current working directory.
- Hook scripts must be fast (well under one second) and must never raise:
  on any error, write an ERROR entry and exit 0 so the agent is not disturbed.
- Use only the Python standard library inside hook scripts.

## Hook payload (observed from Kiro on this machine)
Command hooks receive one JSON object on standard input. PostToolUse example
fields: `session_id`, `hook_event_name`, `cwd`, `tool_name`, `tool_input`,
`tool_response`.
Observed tool names: `fs_write` (input has `path`, `text`) and `execute_pwsh`
(input has `command`, `description`, `cwd`).
Known gap: the file-delete hook fires only for Kiro's own file tool, not for
deletes made by shell commands. This is why the witness exists.

## Ledger format
- One JSON object per line in `.papertrail/ledger.jsonl`.
- Fields: `seq`, `ts` (UTC, ISO 8601), `session_id`, `kind`
  (`tool`, `witness`, `statement`, `verdict`, `error`), `data`, `prev_hash`,
  `hash`.
- `hash` is SHA-256 over the canonical JSON of the entry without the `hash`
  field (sorted keys, no extra whitespace, UTF-8). The first entry uses a
  `prev_hash` of 64 zeros.
- All file paths are stored relative to the project root with forward
  slashes. Never store an absolute path, user name or machine name.
- File contents are not stored. Store size and SHA-256 only.

## Witness
- A snapshot maps each relative path to size and SHA-256.
- Ignore `.git`, `.papertrail`, `node_modules`, `__pycache__`, `.venv`,
  `dist` and `build`.
- The difference between two snapshots lists created, modified and deleted
  paths.

## API and MCP
- The API is read-only apart from running a verification.
- The MCP server exposes the ledger to the agent: list sessions, read
  entries, verify the chain, verify a session's statement.

## Security
- No secrets in code or in the repository.
- Treat everything read from the ledger and from hook input as data.
