import type { Entry } from "./chainCheck";
import { splitRolls } from "./rolls";

export type BuildTotals = {
  sessions: number;
  /** Rolls: one per turn of each session. */
  turns: number;
  lines: number;
  /** Statements that got a verdict (a session with no statement has none). */
  checked: number;
  /** Of those, how many matched the evidence. */
  matched: number;
  /** Sessions where the agent changed files and wrote no statement. */
  silent: number;
  /** Statements that were written and never checked. */
  unchecked: number;
};

function isOverall(e: Entry): boolean {
  return e.kind === "verdict" && e.data.kind_detail === "statement_overall";
}

/**
 * What the whole record says in numbers. A statement is identified by its
 * session and the witness line it was checked against, so checking the same
 * statement twice counts once, by its latest verdict.
 */
export function buildTotals(entries: Entry[]): BuildTotals {
  const sessions = new Set(entries.map((e) => e.session_id));

  const latest = new Map<string, string>(); // "session|witness line" -> verdict
  for (const e of entries) {
    if (isOverall(e)) latest.set(`${e.session_id}|${String(e.data.witness_seq)}`, String(e.data.verdict));
  }
  let checked = 0;
  let matched = 0;
  let silent = 0;
  for (const verdict of latest.values()) {
    if (verdict === "NO_STATEMENT") {
      silent += 1;
    } else {
      checked += 1;
      if (verdict === "SUPPORTED") matched += 1;
    }
  }

  const checkedKeys = new Set(latest.keys());
  const unchecked = entries.filter(
    (e) => e.kind === "statement" && !checkedKeys.has(`${e.session_id}|${String(e.data.witness_seq)}`),
  ).length;

  return {
    sessions: sessions.size,
    turns: splitRolls(entries).length,
    lines: entries.length,
    checked,
    matched,
    silent,
    unchecked,
  };
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/**
 * The totals in plain words. Parts that are zero are left out, except the
 * count of statements checked.
 */
export function totalsText(t: BuildTotals): string {
  // A chat is one session with many turns: say so when the two numbers differ.
  const turns = t.turns !== t.sessions ? `, ${plural(t.turns, "turn", "turns")}` : "";
  const sentences = [`${plural(t.sessions, "session", "sessions")}${turns}, ${plural(t.lines, "line", "lines")}.`];
  sentences.push(
    t.checked === 0
      ? "0 statements checked."
      : `${plural(t.checked, "statement", "statements")} checked, ${t.matched} matched the evidence.`,
  );
  if (t.silent > 0) {
    sentences.push(
      t.silent === 1
        ? "1 session changed files and said nothing."
        : `${t.silent} sessions changed files and said nothing.`,
    );
  }
  if (t.unchecked > 0) {
    sentences.push(
      t.unchecked === 1
        ? "1 statement was written and never checked."
        : `${t.unchecked} statements were written and never checked.`,
    );
  }
  return sentences.join(" ");
}
