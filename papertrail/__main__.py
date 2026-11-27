"""CLI entry point: python -m papertrail <subcommand>."""

import os
import sys
from pathlib import Path

from papertrail import ledger as ledger_mod
from papertrail import statement as statement_mod
from papertrail import verifier as verifier_mod


def _get_root() -> Path:
    env = os.environ.get("PAPERTRAIL_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1]


def _cmd_verify(args: list[str]) -> int:
    if not args:
        print("Usage: python -m papertrail verify <session_id> [<n>]", file=sys.stderr)
        return 1

    session_id = args[0]
    n: int | None = None
    if len(args) >= 2:
        try:
            n = int(args[1])
        except ValueError:
            print(f"Error: statement index must be an integer, got {args[1]!r}", file=sys.stderr)
            return 1

    root = _get_root()
    stmts_dir = root / ".papertrail" / "statements"

    # Find the right statement file.
    if n is not None:
        stmt_path = stmts_dir / f"{session_id}-{n}.json"
        if not stmt_path.exists():
            print(f"Error: no statement found for session {session_id} (index {n})")
            return 1
    else:
        candidates = sorted(stmts_dir.glob(f"{session_id}-*.json"))
        if not candidates:
            print(f"Error: no statement found for session {session_id}")
            return 1
        # Pick the highest numeric suffix.
        def _suffix(p: Path) -> int:
            try:
                return int(p.stem.rsplit("-", 1)[-1])
            except ValueError:
                return 0
        stmt_path = max(candidates, key=_suffix)

    # Parse and verify.
    try:
        stmt = statement_mod.parse(stmt_path)
    except Exception as exc:
        print(f"Error: could not parse statement: {exc}")
        return 1

    ledger_path = root / ".papertrail" / "ledger.jsonl"
    entries = ledger_mod.read(ledger_path)

    result = verifier_mod.verify(stmt, entries, session_id)

    # Format output.
    lines: list[str] = []

    for v in result["verdicts"]:
        verdict_col = f"{v['verdict']:<12}"
        claim_col   = f"{v['claim']:<16}"
        lines.append(f"{verdict_col}  {claim_col}  {v['path']}")

    undeclared_lines: list[str] = []
    for u in result["undeclared"]:
        label_col  = f"{'UNDECLARED':<12}"
        change_col = f"{u['change']:<16}"
        undeclared_lines.append(f"{label_col}  {change_col}  {u['path']}")

    output_parts: list[str] = []
    if lines:
        output_parts.append("\n".join(lines))
    if undeclared_lines:
        output_parts.append("\n".join(undeclared_lines))

    if output_parts:
        print("\n\n".join(output_parts))
        print()  # blank line before OVERALL

    print(f"OVERALL: {result['overall']}")
    return 0


def _cmd_check_chain(args: list[str]) -> int:
    root = _get_root()
    ledger_path = root / ".papertrail" / "ledger.jsonl"

    if not ledger_path.exists():
        print("No ledger found")
        return 0

    entries = ledger_mod.read(ledger_path)
    ok, broken_seq = ledger_mod.verify_chain(ledger_path)
    if ok:
        print(f"Chain OK ({len(entries)} entries)")
        return 0
    else:
        print(f"Chain BROKEN at seq {broken_seq}")
        return 1


DEFAULT_PORT = 8765


def _cmd_serve(args: list[str]) -> int:
    port = DEFAULT_PORT
    if "--port" in args:
        i = args.index("--port")
        try:
            port = int(args[i + 1])
        except (IndexError, ValueError):
            print("Error: --port needs a number, for example --port 9000", file=sys.stderr)
            return 1

    # Imported here so verify and check-chain work without the web packages.
    import uvicorn
    from papertrail.api import app

    print(f"Paper Trail API -> http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print("Usage: python -m papertrail <verify|check-chain|serve> [args]", file=sys.stderr)
        return 1

    cmd, *rest = argv
    if cmd == "verify":
        return _cmd_verify(rest)
    elif cmd == "check-chain":
        return _cmd_check_chain(rest)
    elif cmd == "serve":
        return _cmd_serve(rest)
    else:
        print(f"Unknown subcommand: {cmd!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
