import { describe, expect, it } from "vitest";
import fixture from "@@fixtures/rolls.json";
import type { Entry } from "../lib/chainCheck";
import { rollKey, splitRolls, splitSession, turnLabel } from "../lib/rolls";
import { synthesiseUndeclared } from "../lib/synthesiseUndeclared";
import { demoEntries } from "./demo";

/*
  tests/fixtures/rolls.json is also read by tests/test_rolls.py, so the screen,
  list_sessions and the spool file split a session into the same rolls.
*/

function records(entries: Record<string, unknown>[]): Entry[] {
  return entries.map((e) => ({ ts: "2026-03-04T10:00:00Z", prev_hash: "", hash: "", ...e }) as unknown as Entry);
}

describe("the rolls shared with the Python side", () => {
  it.each(fixture.cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    const got = splitRolls(records(c.entries)).map((r) => ({
      sessionId: r.sessionId,
      number: r.number,
      count: r.count,
      turnStart: r.turnStart,
      seqs: r.entries.map((e) => e.seq),
      title: r.title,
      overall: r.overallVerdict,
      statementNumber: r.statementIndex,
      hasUnverifiedStatement: r.hasUnverifiedStatement,
    }));
    expect(got).toEqual(c.rolls);
  });
});

describe("splitRolls", () => {
  it("gives each roll a key that cannot clash with a session id", () => {
    expect(rollKey("abc", 2)).toBe("abc#2");
    const keys = splitRolls(demoEntries).map((r) => r.key);
    expect(new Set(keys).size).toBe(keys.length);
    expect(keys.every((k) => /#\d+$/.test(k))).toBe(true);
  });

  it("uses the date of the first record of each roll", () => {
    const [roll] = splitRolls(records([{ seq: 1, session_id: "s", kind: "tool", data: {}, ts: "2026-03-04T23:59:59Z" }]));
    expect(roll.date).toBe("2026-03-04");
  });

  it("keeps every record, once, in line order, and never renumbers one", () => {
    for (const c of fixture.cases) {
      const input = records(c.entries);
      const rolls = splitRolls(input);
      const seqs = rolls.flatMap((r) => r.entries.map((e) => e.seq));
      expect([...seqs].sort((a, b) => a - b)).toEqual(input.map((e) => e.seq).sort((a, b) => a - b));
      for (const r of rolls) {
        expect(r.entries.map((e) => e.seq)).toEqual([...r.entries.map((e) => e.seq)].sort((a, b) => a - b));
        for (const e of r.entries) expect(input).toContain(e); // the real record, not a copy
      }
    }
  });

  it("has nothing for no records", () => {
    expect(splitRolls([])).toEqual([]);
    expect(splitSession([])).toEqual([]);
  });

  it("splits the demo: four one-roll sessions and one of two turns", () => {
    const rolls = splitRolls(demoEntries);
    expect(rolls.map((r) => `${r.sessionId}#${r.number}/${r.count}`)).toEqual([
      "demo-session-a#1/1",
      "demo-session-b#1/1",
      "demo-session-c#1/1",
      "demo-session-d#1/2",
      "demo-session-d#2/2",
      "demo-session-e#1/1",
    ]);
    expect(rolls.map((r) => r.title)).toEqual([
      "Read main.py and wrote a notes file.",
      "Cleared the build cache.",
      "No statement written",
      "Wrote the plan.",
      "Cleared two drafts.",
      "Edited the record hook and wrote setup notes.",
    ]);
    expect(rolls.map((r) => r.overallVerdict)).toEqual(["SUPPORTED", "CONTRADICTED", "NO_STATEMENT", "SUPPORTED", "SUPPORTED", "SUPPORTED"]);
    expect(rolls.every((r) => !r.hasUnverifiedStatement)).toBe(true);
    expect(rolls.map((r) => r.statementIndex)).toEqual([1, 1, null, 1, 2, 1]);
  });

  it("puts the between-turns line first in the roll that follows it", () => {
    const second = splitRolls(demoEntries).find((r) => r.key === "demo-session-d#2")!;
    expect(second.entries.map((e) => (e.kind === "witness" ? String(e.data.event) : e.kind)).slice(0, 3)).toEqual([
      "turn",
      "between_turns",
      "tool",
    ]);
  });
});

describe("turnLabel", () => {
  it("names the turn only when the session has more than one", () => {
    expect(turnLabel({ number: 2, count: 3 })).toBe("turn 2 of 3");
    expect(turnLabel({ number: 1, count: 1 })).toBeNull();
  });
});

describe("synthesiseUndeclared", () => {
  const session = demoEntries.filter((e) => e.session_id === "demo-session-b");

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
    const a = demoEntries.filter((e) => e.session_id === "demo-session-a");
    expect(synthesiseUndeclared(a)).toHaveLength(a.length);
  });

  it("never makes an undeclared line out of a between-turns record", () => {
    const second = splitRolls(demoEntries).find((r) => r.key === "demo-session-d#2")!;
    const lines = synthesiseUndeclared(second.entries);
    expect(lines.some((l) => l.kind === "undeclared")).toBe(false);
    expect(lines).toHaveLength(second.entries.length);
  });
});
