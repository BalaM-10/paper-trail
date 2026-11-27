import type { Entry } from "./chainCheck";

export type SessionMeta = {
  sessionId: string;
  /** Summary of the latest statement; the first 8 characters of the id if none. */
  title: string;
  /** "YYYY-MM-DD" of the session's first record. */
  date: string;
  /** Verdict of the latest overall verdict record, or null if never checked. */
  overallVerdict: string | null;
  /** True when the latest statement has no overall verdict yet. */
  hasUnverifiedStatement: boolean;
  /** Which promoted statement to check (1-based, in promotion order), if any. */
  statementIndex: number | null;
};

function isOverall(e: Entry): boolean {
  return e.kind === "verdict" && e.data.kind_detail === "statement_overall";
}

/** One summary per session, in the order sessions first appear. */
export function buildSessionMeta(entries: Entry[]): SessionMeta[] {
  const order: string[] = [];
  const bySession = new Map<string, Entry[]>();
  for (const e of entries) {
    if (!bySession.has(e.session_id)) {
      bySession.set(e.session_id, []);
      order.push(e.session_id);
    }
    bySession.get(e.session_id)!.push(e);
  }

  return order.map((sessionId) => {
    const mine = bySession.get(sessionId)!;
    const statements = mine.filter((e) => e.kind === "statement");
    const checked = new Set(
      mine.filter(isOverall).map((e) => e.data.witness_seq as number),
    );
    const overalls = mine.filter(isOverall);

    const latest = statements[statements.length - 1];
    const latestChecked = latest ? checked.has(latest.data.witness_seq as number) : false;

    return {
      sessionId,
      title: latest
        ? String(latest.data.summary ?? sessionId.slice(0, 8))
        : overalls.length > 0 && overalls[overalls.length - 1].data.verdict === "NO_STATEMENT"
          ? "No statement written"
          : sessionId.slice(0, 8),
      date: mine[0].ts.slice(0, 10),
      overallVerdict: overalls.length ? String(overalls[overalls.length - 1].data.verdict) : null,
      hasUnverifiedStatement: latest !== undefined && !latestChecked,
      statementIndex: latest !== undefined ? statements.length : null,
    };
  });
}
