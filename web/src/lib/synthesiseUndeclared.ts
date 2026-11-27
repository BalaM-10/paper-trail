import type { Entry } from "./chainCheck";
import type { UndeclaredItem } from "./entryText";

/** A record, or a line made up for display (never part of the checked paper). */
export type DisplayEntry = Entry & { _synthetic?: true };

/**
 * For each overall verdict, insert one line per undeclared change immediately
 * BEFORE it, so the overall verdict is always the last line of its statement.
 * Each made-up line carries the number of the witness line that proves it.
 */
export function synthesiseUndeclared(entries: Entry[]): DisplayEntry[] {
  const out: DisplayEntry[] = [];
  for (const e of entries) {
    if (e.kind === "verdict" && e.data.kind_detail === "statement_overall") {
      const undeclared = (e.data.undeclared ?? []) as UndeclaredItem[];
      for (const item of undeclared) {
        out.push({
          seq: -(out.length + 1), // negative: never collides with a real record
          ts: e.ts,
          session_id: e.session_id,
          kind: "undeclared",
          data: { ...item, witnessSeq: e.data.witness_seq },
          prev_hash: "",
          hash: "",
          _synthetic: true,
        });
      }
    }
    out.push(e);
  }
  return out;
}
