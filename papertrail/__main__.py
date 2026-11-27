"""CLI entry point: python -m papertrail <subcommand>."""

import os
import sys
from pathlib import Path

from papertrail import ledger as ledger_mod
from papertrail import archive as archive_mod, install, outcome, spool


def _get_root() -> Path:
    env = os.environ.get("PAPERTRAIL_ROOT")
    if env:
        return Path(env)
    return Path.cwd()  # the project; not the folder the package is installed in


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


def _cmd_archive(args: list[str]) -> int:
    """Move the record to .papertrail/archive/ so the next record starts clean."""
    if args:
        print("Usage: python -m papertrail archive", file=sys.stderr)
        return 1
    try:
        done = archive_mod.archive(_get_root())
    except archive_mod.ArchiveError as exc:
        print(f"Did not archive: {exc}. Nothing was moved.")
        return 1
    except OSError as exc:
        print(f"Did not archive: {exc.strerror or exc}. Nothing was moved.")
        return 1
    for line in archive_mod.describe(done):
        print(line)
    return 0


def _cmd_init(args: list[str]) -> int:
    """Set up Paper Trail in another Kiro project."""
    force = "--force" in args
    folders = [a for a in args if a != "--force"]
    if len(folders) != 1:
        print("Usage: python -m papertrail init <project_folder> [--force]", file=sys.stderr)
        return 1
    folder = Path(folders[0])
    try:
        steps = install.init(folder, force=force)
    except NotADirectoryError:
        print(f"Error: {folder} is not a folder. Nothing was changed.", file=sys.stderr)
        return 1
    for step in steps:
        print(install.describe(step))
    print()
    if install.succeeded(steps):
        print(f"Paper Trail is set up in {folder}.")
        print(f"Next: run  python -m papertrail doctor {folder}  to check the setup.")
        return 0
    print("Some files were left alone or could not be set up. See the lines above.")
    return 1


def _cmd_doctor(args: list[str]) -> int:
    """Say what is missing from an installed project."""
    if len(args) > 1:
        print("Usage: python -m papertrail doctor [project_folder]", file=sys.stderr)
        return 1
    folder = Path(args[0]) if args else Path.cwd()
    try:
        checks = install.doctor(folder)
    except NotADirectoryError:
        print(f"Error: {folder} is not a folder.", file=sys.stderr)
        return 1
    for check in checks:
        for line in install.describe_check(check):
            print(line)
    print()
    missing = sum(1 for c in checks if c.level == "missing")
    if missing:
        print(f"{missing} {'thing is' if missing == 1 else 'things are'} missing. Paper Trail will not record properly until that is fixed.")
        return 1
    print("Everything Paper Trail needs is in place.")
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
        print("Usage: python -m papertrail <verify|check-chain|print|archive|init|doctor|serve> [args]", file=sys.stderr)
        return 1

    cmd, *rest = argv
    if cmd == "verify":
        return _cmd_verify(rest)
    elif cmd == "check-chain":
        return _cmd_check_chain(rest)
    elif cmd == "print":
        return _cmd_print(rest)
    elif cmd == "archive":
        return _cmd_archive(rest)
    elif cmd == "init":
        return _cmd_init(rest)
    elif cmd == "doctor":
        return _cmd_doctor(rest)
    elif cmd == "serve":
        return _cmd_serve(rest)
    else:
        print(f"Unknown subcommand: {cmd!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
