import type { Entry } from "./chainCheck";

/*
  A session split into rolls, one per turn. This is the twin of papertrail/rolls.py;
  tests/fixtures/rolls.json is read by tests in both languages.

  Kiro keeps one session id across many replies. A turn is one reply: it starts
  with a "turn" witness record (the person sent a prompt) and ends with the
  agent's stop and the verdict on its statement. Each turn is its own roll.

  1. A session with no turn record is one roll, exactly as before.
  2. Otherwise roll k holds the records from turn start k up to the next one.
     Records before the first turn start (the session start) join roll 1, so a
     tool call belongs to the turn it happened in.
  3. A verdict record belongs to the roll of the stop it checked (its witness_seq),
     even if it was written later.
  4. Line numbers are never changed: a roll holds the real records.
*/

export const NO_STATEMENT_TITLE = "No statement written";
export const NOTHING_CHANGED_TITLE = "Nothing changed";
export const IN_PROGRESS_TITLE = "Turn in progress";

export type Roll = {
  /** Unique on the page: "<session id>#<number>". A session id never holds "#". */
  key: string;
  sessionId: string;
  /** 1-based, within the session. */
  number: number;
  /** How many rolls the session has. */
  count: number;
  /** The session has turn records, so "turn n of N" means something. */
  turnStart: boolean;
  entries: Entry[];
  /** The roll's statement; or what happened when there is none. */
  title: string;
  /** "YYYY-MM-DD" of the roll's first record. */
  date: string;
  /** Verdict of the newest overall verdict in the roll, or null if never checked. */
  overallVerdict: string | null;
  /** True when the roll's newest statement has no overall verdict yet. */
  hasUnverifiedStatement: boolean;
  /** Which promoted statement of the session to check (1-based), if any. */
  statementIndex: number | null;
};

export function rollKey(sessionId: string, number: number): string {
  return `${sessionId}#${number}`;
}

function isTurnStart(e: Entry): boolean {
  return e.kind === "witness" && e.data.event === "turn";
}

function isOverall(e: Entry): boolean {
  return e.kind === "verdict" && e.data.kind_detail === "statement_overall";
}

function titleOf(sessionId: string, entries: Entry[], turnStart: boolean, overall: string | null): string {
  const statements = entries.filter((e) => e.kind === "statement");
  if (statements.length > 0) {
    const summary = statements[statements.length - 1].data.summary;
    return summary !== undefined && summary !== null ? String(summary) : sessionId.slice(0, 8);
  }
  if (overall === "NO_STATEMENT") return NO_STATEMENT_TITLE;
  if (turnStart) {
    const stopped = entries.some((e) => e.kind === "witness" && e.data.event === "stop");
    return stopped ? NOTHING_CHANGED_TITLE : IN_PROGRESS_TITLE;
  }
  return sessionId.slice(0, 8);
}

/** The rolls of ONE session. `entries` are its records, in order. */
export function splitSession(entries: Entry[]): Roll[] {
  if (entries.length === 0) return [];
  const sessionId = entries[0].session_id;
  const starts = entries.flatMap((e, i) => (isTurnStart(e) ? [i] : []));
  const turnStart = starts.length > 0;

  let groups: Entry[][];
  if (!turnStart) {
    groups = [[...entries]];
  } else {
    const bounds = [0, ...starts.slice(1), entries.length];
    groups = starts.map((_, k) => entries.slice(bounds[k], bounds[k + 1]));
  }

  // A verdict belongs to the roll of the stop it checked.
  const home = new Map<number, number>();
  groups.forEach((group, k) =>
    group.forEach((e) => {
      if (e.kind === "witness") home.set(e.seq, k);
    }),
  );
  const moved = groups.map((group) => [...group]);
  groups.forEach((group, k) =>
    group.forEach((e) => {
      if (e.kind !== "verdict") return;
      const target = home.get(e.data.witness_seq as number);
      if (target !== undefined && target !== k) {
        moved[k] = moved[k].filter((x) => x !== e);
        moved[target].push(e);
      }
    }),
  );
  groups = moved.map((group) => [...group].sort((a, b) => a.seq - b.seq));

  const statements = entries.filter((e) => e.kind === "statement");
  const checked = new Set(entries.filter(isOverall).map((e) => e.data.witness_seq));

  return groups.map((group, k) => {
    const overalls = group.filter(isOverall);
    const overall = overalls.length > 0 ? String(overalls[overalls.length - 1].data.verdict) : null;
    const mine = group.filter((e) => e.kind === "statement");
    const latest = mine.length > 0 ? mine[mine.length - 1] : undefined;
    return {
      key: rollKey(sessionId, k + 1),
      sessionId,
      number: k + 1,
      count: groups.length,
      turnStart,
      entries: group,
      title: titleOf(sessionId, group, turnStart, overall),
      date: String(group[0].ts ?? "").slice(0, 10),
      overallVerdict: overall,
      hasUnverifiedStatement: latest !== undefined && !checked.has(latest.data.witness_seq),
      statementIndex: latest !== undefined ? statements.findIndex((s) => s.seq === latest.seq) + 1 : null,
    };
  });
}

/** The rolls of every session, in the order the sessions first appear. */
export function splitRolls(entries: Entry[]): Roll[] {
  const order: string[] = [];
  const bySession = new Map<string, Entry[]>();
  for (const e of entries) {
    if (!bySession.has(e.session_id)) {
      bySession.set(e.session_id, []);
      order.push(e.session_id);
    }
    bySession.get(e.session_id)!.push(e);
  }
  return order.flatMap((sessionId) => splitSession(bySession.get(sessionId)!));
}

/** "turn 2 of 3" for a session that has more than one turn; otherwise nothing. */
export function turnLabel(roll: Pick<Roll, "number" | "count">): string | null {
  return roll.count > 1 ? `turn ${roll.number} of ${roll.count}` : null;
}
