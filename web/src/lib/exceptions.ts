import type { DisplayEntry } from "./synthesiseUndeclared";

/*
  EXCEPTIONS ONLY: what a roll keeps when the key is down. Only lines that need a person's
  eye stay on the paper:
    - a claim that is CONTRADICTED or UNVERIFIED, and an overall verdict that is not SUPPORTED
      (which includes NO STATEMENT),
    - a change the witness saw that the statement never mentioned,
    - a between-turns line,
    - a line saying the recording setup changed,
    - the line where the paper is torn (the record was edited after it was written).
  Everything else is hidden, and the page says how many lines that is.
*/

export const NOTHING_TO_FLAG = "Nothing to flag in this turn.";

/** True when the line must stay on the paper. `brokenAt` is the torn line, if any. */
export function isException(entry: DisplayEntry, brokenAt: number | null): boolean {
  if (!entry._synthetic && brokenAt !== null && entry.seq === brokenAt) return true;
  switch (entry.kind) {
    case "undeclared":
      return true;
    case "verdict":
      return entry.data.verdict !== "SUPPORTED";
    case "witness":
      return entry.data.event === "between_turns" || entry.data.event === "setup_changed";
    default:
      return false;
  }
}

/** The lines that stay, and how many were hidden. */
export function exceptionsOnly(
  lines: DisplayEntry[],
  brokenAt: number | null,
): { shown: DisplayEntry[]; hidden: number } {
  const shown = lines.filter((l) => isException(l, brokenAt));
  return { shown, hidden: lines.length - shown.length };
}

/** "3 lines hidden." */
export function hiddenText(hidden: number): string {
  if (hidden === 0) return "No lines hidden.";
  return `${hidden} ${hidden === 1 ? "line" : "lines"} hidden.`;
}
