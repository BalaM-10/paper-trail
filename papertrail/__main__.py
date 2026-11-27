"""CLI entry point: python -m papertrail <subcommand>."""

import os
import sys
from pathlib import Path

from papertrail import ledger as ledger_mod
from papertrail import outcome, spool


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

    # A numbered statement, or (no number) whichever is newer: the latest statement
    # or a NO_STATEMENT verdict the stop hook recorded.
    try:
        result = outcome.result_for(root, session_id, n)
    except ValueError as exc:
        print(f"Error: could not parse statement: {exc}")
        return 1
    except OSError as exc:
        print(f"Error: {exc}")
        return 1

    if result is None:
        where = f" (index {n})" if n is not None else ""
        print(f"Error: no statement found for session {session_id}{where}")
        return 1

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


def _cmd_print(args: list[str]) -> int:
    """Write .papertrail/spool/<session_id>.txt, ready for a printer."""
    if not args:
        print("Usage: python -m papertrail print <session_id>", file=sys.stderr)
        return 1

    session_id = args[0]
    if not outcome.valid_session_id(session_id):
        print(f"Error: {session_id!r} is not a usable session id", file=sys.stderr)
        return 1

    root = _get_root()
    try:
        path = spool.write(root, session_id)
    except LookupError:
        print(f"Error: no records found for session {session_id}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {path.relative_to(root).as_posix()}")
    return 0


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
        print("Usage: python -m papertrail <verify|check-chain|print|serve> [args]", file=sys.stderr)
        return 1

    cmd, *rest = argv
    if cmd == "verify":
        return _cmd_verify(rest)
    elif cmd == "check-chain":
        return _cmd_check_chain(rest)
    elif cmd == "print":
        return _cmd_print(rest)
    elif cmd == "serve":
        return _cmd_serve(rest)
    else:
        print(f"Unknown subcommand: {cmd!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
