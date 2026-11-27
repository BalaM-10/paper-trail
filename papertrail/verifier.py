"""Verify an agent statement against ledger evidence and witness diff."""

import sys
from pathlib import Path

from papertrail import ledger as ledger_mod
from papertrail.witness import EXCLUDE


def _norm(p: str) -> str:
    """Unify separators; lowercase on Windows for case-insensitive match."""
    p = p.replace("\\", "/")
    if sys.platform == "win32":
        p = p.lower()
    return p


def _in_excluded(path: str) -> bool:
    """True if any path segment is in EXCLUDE."""
    return any(seg in EXCLUDE for seg in _norm(path).split("/"))


def verify(
    statement: dict,
    ledger_entries: list[dict],
    session_id: str,
    ledger_path: Path | None = None,
) -> dict:
    """
    Verify every file claim in statement against ledger_entries.

    Returns:
        {
            "verdicts":   [{"path", "claim", "verdict", "evidence_seq"}, ...],
            "undeclared": [{"path", "change"}, ...],
            "overall":    str,
        }

    Idempotent: if a verdict entry with data.kind_detail == "statement_overall"
    and data.witness_seq == statement["witness_seq"] already exists in
    ledger_entries, the stored result is reconstructed and returned without
    appending anything new.

    ledger_path: where verdict entries are appended. When omitted it is
    derived from PAPERTRAIL_ROOT, or the project root if that is unset.
    Callers that must not touch the project's own ledger pass it explicitly.
    """
    witness_seq: int = statement["witness_seq"]

    # ------------------------------------------------------------------ #
    # Idempotency: return stored result if overall verdict already exists  #
    # ------------------------------------------------------------------ #
    existing_overall = next(
        (
            e for e in ledger_entries
            if e["kind"] == "verdict"
            and e["data"].get("kind_detail") == "statement_overall"
            and e["data"].get("witness_seq") == witness_seq
        ),
        None,
    )
    if existing_overall is not None:
        per_path = [
            {
                "path":         e["data"]["path"],
                "claim":        e["data"]["claim"],
                "verdict":      e["data"]["verdict"],
                "evidence_seq": e["data"]["evidence_seq"],
            }
            for e in ledger_entries
            if e["kind"] == "verdict"
            and e["data"].get("witness_seq") == witness_seq
            and e["data"].get("kind_detail") != "statement_overall"
            and "path" in e["data"]
        ]
        undeclared = existing_overall["data"].get("undeclared", [])
        return {
            "verdicts":   per_path,
            "undeclared": undeclared,
            "overall":    existing_overall["data"]["verdict"],
        }

    # ------------------------------------------------------------------ #
    # Find the witness/stop entry                                          #
    # ------------------------------------------------------------------ #
    witness_entry = next(
        (
            e for e in ledger_entries
            if e["seq"] == witness_seq and e["kind"] == "witness"
        ),
        None,
    )

    has_diff = (
        witness_entry is not None
        and witness_entry["data"].get("baseline", "none") != "none"
    )

    if has_diff:
        raw_diff = witness_entry["data"]["diff"]
        norm_created  = {_norm(p) for p in raw_diff.get("created",  [])}
        norm_modified = {_norm(p) for p in raw_diff.get("modified", [])}
        norm_deleted  = {_norm(p) for p in raw_diff.get("deleted",  [])}
    else:
        norm_created = norm_modified = norm_deleted = set()

    # ------------------------------------------------------------------ #
    # Build tool-entry index for files_read                               #
    # ------------------------------------------------------------------ #
    # Map normalised path → list[seq] from tool entries in this session.
    # A read in an earlier turn is not evidence for this turn's statement: when the
    # session has turn starts, only the tool calls between the start of the turn this
    # stop closes and the stop count. Without turn starts, the whole session counts.
    turn_seq = max(
        (
            e["seq"] for e in ledger_entries
            if e["kind"] == "witness"
            and e.get("session_id") == session_id
            and e["data"].get("event") == "turn"
            and e["seq"] < witness_seq
        ),
        default=None,
    )
    tool_path_index: dict[str, list[int]] = {}
    for e in ledger_entries:
        if e["kind"] != "tool" or e.get("session_id") != session_id:
            continue
        if turn_seq is not None and not (turn_seq < e["seq"] < witness_seq):
            continue
        ti = e["data"].get("tool_input") or {}
        for v in ti.values():
            if isinstance(v, str):
                tool_path_index.setdefault(_norm(v), []).append(e["seq"])

    # ------------------------------------------------------------------ #
    # Verdict table                                                        #
    # ------------------------------------------------------------------ #
    verdicts: list[dict] = []

    # files_created, files_modified, files_deleted
    claim_map = {
        "files_created":  norm_created,
        "files_modified": norm_modified,
        "files_deleted":  norm_deleted,
    }
    for claim_key, norm_set in claim_map.items():
        for path in statement.get(claim_key, []):
            if not has_diff:
                verdicts.append({
                    "path":         path,
                    "claim":        claim_key,
                    "verdict":      "UNVERIFIED",
                    "evidence_seq": [],
                })
            elif _in_excluded(path):
                verdicts.append({
                    "path":         path,
                    "claim":        claim_key,
                    "verdict":      "UNVERIFIED",
                    "evidence_seq": [],
                })
            elif _norm(path) in norm_set:
                verdicts.append({
                    "path":         path,
                    "claim":        claim_key,
                    "verdict":      "SUPPORTED",
                    "evidence_seq": [witness_seq],
                })
            else:
                verdicts.append({
                    "path":         path,
                    "claim":        claim_key,
                    "verdict":      "CONTRADICTED",
                    "evidence_seq": [witness_seq],
                })

    # files_read — never CONTRADICTED
    for path in statement.get("files_read", []):
        seqs = tool_path_index.get(_norm(path), [])
        if seqs:
            verdicts.append({
                "path":         path,
                "claim":        "files_read",
                "verdict":      "SUPPORTED",
                "evidence_seq": seqs,
            })
        else:
            verdicts.append({
                "path":         path,
                "claim":        "files_read",
                "verdict":      "UNVERIFIED",
                "evidence_seq": [],
            })

    # ------------------------------------------------------------------ #
    # Undeclared changes                                                   #
    # ------------------------------------------------------------------ #
    undeclared: list[dict] = []
    if has_diff:
        all_claimed = {
            _norm(p)
            for key in ("files_created", "files_modified", "files_deleted")
            for p in statement.get(key, [])
        }
        for change, paths in (
            ("created",  raw_diff.get("created",  [])),
            ("modified", raw_diff.get("modified", [])),
            ("deleted",  raw_diff.get("deleted",  [])),
        ):
            for p in paths:
                if _norm(p) not in all_claimed:
                    undeclared.append({"path": p, "change": change})

    # ------------------------------------------------------------------ #
    # Overall verdict                                                      #
    # ------------------------------------------------------------------ #
    if any(v["verdict"] == "CONTRADICTED" for v in verdicts) or undeclared:
        overall = "CONTRADICTED"
    elif all(v["verdict"] == "SUPPORTED" for v in verdicts):
        overall = "SUPPORTED"
    else:
        overall = "UNVERIFIED"

    # ------------------------------------------------------------------ #
    # Ledger writes                                                        #
    # ------------------------------------------------------------------ #
    if ledger_path is None:
        ledger_path = _find_ledger_path(ledger_entries)

    for v in verdicts:
        ledger_mod.append(ledger_path, session_id, "verdict", {
            "path":         v["path"],
            "claim":        v["claim"],
            "verdict":      v["verdict"],
            "evidence_seq": v["evidence_seq"],
            "witness_seq":  witness_seq,
        })

    all_evidence = sorted({seq for v in verdicts for seq in v["evidence_seq"]})
    ledger_mod.append(ledger_path, session_id, "verdict", {
        "kind_detail":  "statement_overall",
        "verdict":      overall,
        "evidence_seq": all_evidence,
        "witness_seq":  witness_seq,
        "undeclared":   undeclared,
    })

    return {
        "verdicts":   verdicts,
        "undeclared": undeclared,
        "overall":    overall,
    }


def _find_ledger_path(ledger_entries: list[dict]) -> Path:
    """
    The verifier needs the ledger path to append verdict entries.  We receive
    entries (not the path), so we derive the path from the PAPERTRAIL_ROOT
    environment variable when set, or from the caller's location otherwise.
    Tests always set PAPERTRAIL_ROOT.
    """
    import os
    env_root = os.environ.get("PAPERTRAIL_ROOT")
    if env_root:
        return Path(env_root) / ".papertrail" / "ledger.jsonl"
    # Fall back: two levels up from this file is the project root.
    return Path(__file__).resolve().parents[1] / ".papertrail" / "ledger.jsonl"
