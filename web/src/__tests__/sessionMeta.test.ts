import { describe, expect, it } from "vitest";
import type { Entry } from "../lib/chainCheck";
import { buildSessionMeta } from "../lib/sessionMeta";
import { synthesiseUndeclared } from "../lib/synthesiseUndeclared";
import demoLedgerRaw from "../../public/demo/ledger.jsonl?raw";

let n = 0;
function entry(sid: string, kind: string, data: Record<string, unknown>): Entry {
  n += 1;
  return { seq: n, ts: "2026-03-04T10:00:00Z", session_id: sid, kind, data, prev_hash: "", hash: "" };
}

const demo = demoLedgerRaw
  .split(/\r?\n/)
  .filter((l) => l.trim())
  .map((l) => JSON.parse(l) as Entry);

describe("buildSessionMeta", () => {
  it("titles each session by its statement summary", () => {
    const metas = buildSessionMeta(demo);
    expect(metas.map((m) => m.title)).toEqual([
      "Read main.py and wrote a notes file.",
      "Cleared the build cache.",
      "No statement written",
    ]);
    expect(metas.map((m) => m.overallVerdict)).toEqual(["SUPPORTED", "CONTRADICTED", "NO_STATEMENT"]);
    expect(metas.every((m) => !m.hasUnverifiedStatement)).toBe(true);
  });

  it("falls back to the first 8 characters of the id with no statement", () => {
    const [m] = buildSessionMeta([entry("abcdef1234567890", "tool", {})]);
    expect(m.title).toBe("abcdef12");
    expect(m.statementIndex).toBeNull();
    expect(m.hasUnverifiedStatement).toBe(false);
    expect(m.overallVerdict).toBeNull();
  });

  it("flags a statement that has no overall verdict yet, and numbers it", () => {
    const [m] = buildSessionMeta([
      entry("s1", "statement", { summary: "First.", witness_seq: 2 }),
      entry("s1", "verdict", { kind_detail: "statement_overall", verdict: "SUPPORTED", witness_seq: 2 }),
      entry("s1", "statement", { summary: "Second.", witness_seq: 9 }),
    ]);
    expect(m.title).toBe("Second.");
    expect(m.hasUnverifiedStatement).toBe(true);
    expect(m.statementIndex).toBe(2);
    expect(m.overallVerdict).toBe("SUPPORTED");
  });

  it("uses the date of the first record", () => {
    expect(buildSessionMeta([entry("s", "tool", {})])[0].date).toBe("2026-03-04");
  });
});

describe("synthesiseUndeclared", () => {
  const session = demo.filter((e) => e.session_id === "demo-session-b");

  it("puts the undeclared line after the per-path verdicts and before the overall verdict", () => {
    const lines = synthesiseUndeclared(session);
    const kinds = lines.map((l) => l.kind);
    expect(kinds.slice(-3)).toEqual(["verdict", "undeclared", "verdict"]);
    const last = lines[lines.length - 1];
    expect(last.kind).toBe("verdict");
    expect(last.data.kind_detail).toBe("statement_overall");
  });

  it("links the undeclared line to the witness line that proves it", () => {
    const line = synthesiseUndeclared(session).find((l) => l.kind === "undeclared")!;
    expect(line.data.path).toBe("sample/notes.txt");
    expect(line.data.change).toBe("deleted");
    const witnessStop = session.find((e) => e.kind === "witness" && e.data.event === "stop")!;
    expect(line.data.witnessSeq).toBe(witnessStop.seq);
    expect(line.seq).toBeLessThan(0);
  });

  it("adds nothing for a session with no undeclared changes", () => {
    const a = demo.filter((e) => e.session_id === "demo-session-a");
    expect(synthesiseUndeclared(a)).toHaveLength(a.length);
  });
});
