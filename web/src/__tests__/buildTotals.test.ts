import { describe, expect, it } from "vitest";
import { buildTotals, totalsText } from "../lib/buildTotals";
import type { Entry } from "../lib/chainCheck";
import { makeRecord } from "./buildRecord";
import { demoEntries } from "./demo";

describe("what the record adds up to", () => {
  it("counts the demo: five sessions in six turns, five statements checked, four matched, one said nothing", () => {
    const totals = buildTotals(demoEntries);
    expect(totals).toEqual({ sessions: 5, turns: 6, lines: 44, checked: 5, matched: 4, silent: 1, unchecked: 0 });
    expect(totalsText(totals)).toBe(
      "5 sessions, 6 turns, 44 lines. 5 statements checked, 4 matched the evidence. 1 session changed files and said nothing.",
    );
  });

  it("says turns only when a session holds more than one", async () => {
    const { entries } = await makeRecord([
      { id: "a", tools: 1, outcome: "supported" },
      { id: "b", tools: 1, outcome: "supported" },
    ]);
    const totals = buildTotals(entries);
    expect([totals.sessions, totals.turns]).toEqual([2, 2]);
    expect(totalsText(totals)).toMatch(/^2 sessions, \d+ lines\./);
    expect(totalsText({ ...totals, sessions: 1, turns: 7 })).toMatch(/^1 session, 7 turns, \d+ lines\./);
    expect(totalsText({ ...totals, sessions: 1, turns: 1 })).toMatch(/^1 session, \d+ lines\./);
  });

  it("counts statements that were written and never checked", async () => {
    const { entries } = await makeRecord([
      { id: "a", tools: 1, outcome: "supported" },
      { id: "b", tools: 1, outcome: "unchecked" },
      { id: "c", tools: 1, outcome: "unchecked" },
    ]);
    const totals = buildTotals(entries);
    expect([totals.checked, totals.matched, totals.unchecked]).toEqual([1, 1, 2]);
    expect(totalsText(totals)).toContain("2 statements were written and never checked.");
  });

  it("says 1 statement, 1 session and 1 line in the singular", () => {
    const one: Entry[] = [
      { seq: 1, ts: "", session_id: "a", kind: "witness", data: { event: "start" }, prev_hash: "", hash: "h" },
    ];
    expect(totalsText(buildTotals(one))).toBe("1 session, 1 line. 0 statements checked.");
    const text = totalsText({ sessions: 1, turns: 1, lines: 2, checked: 1, matched: 0, silent: 1, unchecked: 1 });
    expect(text).toBe(
      "1 session, 2 lines. 1 statement checked, 0 matched the evidence. 1 session changed files and said nothing. 1 statement was written and never checked.",
    );
  });

  it("leaves out the parts that are zero, except the statements checked", () => {
    const text = totalsText({ sessions: 4, turns: 4, lines: 40, checked: 0, matched: 0, silent: 0, unchecked: 0 });
    expect(text).toBe("4 sessions, 40 lines. 0 statements checked.");
    expect(text).not.toMatch(/nothing|never/);
  });

  it("counts the same statement once, by its latest verdict", () => {
    const base = { ts: "", prev_hash: "", hash: "h", session_id: "a", kind: "verdict" };
    const overall = (seq: number, verdict: string): Entry => ({
      ...base,
      seq,
      data: { kind_detail: "statement_overall", verdict, witness_seq: 4 },
    });
    const statement: Entry = {
      ...base,
      seq: 5,
      kind: "statement",
      data: { summary: "x", witness_seq: 4 },
    };
    const totals = buildTotals([statement, overall(6, "CONTRADICTED"), overall(7, "SUPPORTED")]);
    expect([totals.checked, totals.matched, totals.unchecked]).toEqual([1, 1, 0]);
  });

  it("uses no word the page may not show", () => {
    const text = totalsText({ sessions: 5, turns: 9, lines: 600, checked: 3, matched: 2, silent: 2, unchecked: 3 });
    expect(text).not.toMatch(/\b(hash|chain|ledger|entry|entries|seq|jsonl|sha-?256|canonical|hex)\b/i);
  });
});
