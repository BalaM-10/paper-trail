import { describe, expect, it } from "vitest";
import { NOTHING_TO_FLAG, exceptionsOnly, hiddenText, isException } from "../lib/exceptions";
import { synthesiseUndeclared, type DisplayEntry } from "../lib/synthesiseUndeclared";
import { SESSION_A, SESSION_B, SESSION_C, demoEntries, sessionOf } from "./demo";

function line(kind: string, data: Record<string, unknown>, seq = 1): DisplayEntry {
  return { seq, ts: "", session_id: "s", kind, data, prev_hash: "", hash: "" };
}

describe("which lines EXCEPTIONS ONLY keeps", () => {
  it("keeps CONTRADICTED and UNVERIFIED claims, and drops SUPPORTED ones", () => {
    expect(isException(line("verdict", { verdict: "CONTRADICTED", path: "a" }), null)).toBe(true);
    expect(isException(line("verdict", { verdict: "UNVERIFIED", path: "a" }), null)).toBe(true);
    expect(isException(line("verdict", { verdict: "SUPPORTED", path: "a" }), null)).toBe(false);
  });

  it("keeps an overall verdict that is not SUPPORTED, NO STATEMENT included", () => {
    const overall = (verdict: string) => line("verdict", { kind_detail: "statement_overall", verdict });
    expect(isException(overall("CONTRADICTED"), null)).toBe(true);
    expect(isException(overall("UNVERIFIED"), null)).toBe(true);
    expect(isException(overall("NO_STATEMENT"), null)).toBe(true);
    expect(isException(overall("SUPPORTED"), null)).toBe(false);
  });

  it("keeps changes the agent never mentioned, between-turns lines and setup lines", () => {
    expect(isException(line("undeclared", { path: "a", change: "deleted" }), null)).toBe(true);
    expect(isException(line("witness", { event: "between_turns" }), null)).toBe(true);
    expect(isException(line("witness", { event: "setup_changed", files: [".kiro/hooks/a"] }), null)).toBe(true);
  });

  it("drops everything else: snapshots, tool calls and the statement itself", () => {
    for (const e of [
      line("witness", { event: "start" }),
      line("witness", { event: "turn" }),
      line("witness", { event: "stop" }),
      line("tool", { tool_name: "read_file" }),
      line("statement", { summary: "x" }),
      line("error", { error: "x" }),
    ]) {
      expect(isException(e, null)).toBe(false);
    }
  });

  it("keeps the line where the paper is torn, whatever it is, and only that line", () => {
    const tool = line("tool", { tool_name: "read_file" }, 7);
    expect(isException(tool, 7)).toBe(true);
    expect(isException(tool, 8)).toBe(false);
    // a made-up line has a negative number and is never the torn one
    expect(isException({ ...line("statement", {}, -7), _synthetic: true }, -7)).toBe(false);
  });
});

describe("what it says about the lines it hides", () => {
  it("counts the hidden lines, in the singular too", () => {
    expect(hiddenText(0)).toBe("No lines hidden.");
    expect(hiddenText(1)).toBe("1 line hidden.");
    expect(hiddenText(12)).toBe("12 lines hidden.");
  });

  it("has the words for a roll with nothing to flag", () => {
    expect(NOTHING_TO_FLAG).toBe("Nothing to flag in this turn.");
  });
});

describe("on the demo's rolls", () => {
  it("keeps nothing from the honest session, and counts every line as hidden", () => {
    const lines = synthesiseUndeclared(sessionOf(SESSION_A));
    const { shown, hidden } = exceptionsOnly(lines, null);
    expect(shown).toEqual([]);
    expect(hidden).toBe(lines.length);
  });

  it("keeps the cleanup story's undeclared file and its CONTRADICTED verdict", () => {
    const lines = synthesiseUndeclared(sessionOf(SESSION_B));
    const { shown, hidden } = exceptionsOnly(lines, null);
    expect(shown.map((l) => l.kind)).toEqual(["undeclared", "verdict"]);
    expect(shown[1].data.verdict).toBe("CONTRADICTED");
    expect(shown.length + hidden).toBe(lines.length);
  });

  it("keeps NO STATEMENT and the changes the witness saw", () => {
    const { shown } = exceptionsOnly(synthesiseUndeclared(sessionOf(SESSION_C)), null);
    expect(shown.filter((l) => l.kind === "undeclared")).toHaveLength(2);
    expect(shown[shown.length - 1].data.verdict).toBe("NO_STATEMENT");
  });

  it("keeps the between-turns line and the setup line wherever the demo has them", () => {
    const { shown } = exceptionsOnly(synthesiseUndeclared(demoEntries), null);
    const events = shown.filter((l) => l.kind === "witness").map((l) => l.data.event);
    expect(events).toEqual(["between_turns", "setup_changed"]);
  });
});
