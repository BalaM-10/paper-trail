import { describe, expect, it } from "vitest";
import type { Entry } from "../lib/chainCheck";
import { coverageText, plainDate } from "../lib/coverage";

const at = (ts: string): Entry => ({ seq: 1, ts, session_id: "s", kind: "tool", data: {}, prev_hash: "", hash: "h" });

describe("dates in plain words", () => {
  it.each([
    ["2026-03-01T09:00:00.123456Z", "1 March 2026"],
    ["2026-12-31T23:59:59Z", "31 December 2026"],
    ["2027-01-09T00:00:00+00:00", "9 January 2027"],
  ])("%s is %s", (ts, text) => expect(plainDate(ts)).toBe(text));

  it.each(["", "yesterday", "2026-13-01T00:00:00Z", "2026-00-10T00:00:00Z"])("%j is not a date", (ts) =>
    expect(plainDate(ts)).toBeNull(),
  );
});

describe("which dates the record covers", () => {
  const first = at("2026-03-01T09:00:00Z");
  const last = at("2026-03-04T17:30:00Z");

  it("names the dates of the first and the last line", () => {
    expect(coverageText([first, at("2026-03-02T10:00:00Z"), last], null)).toBe(
      "This record runs from 1 March 2026 to 4 March 2026.",
    );
  });

  it("says it is from one day when both lines are on one day", () => {
    expect(coverageText([first, at("2026-03-01T18:00:00Z")], null)).toBe("This record is from 1 March 2026.");
    expect(coverageText([first], false)).toBe("This record is from 1 March 2026.");
  });

  it("says it covers only part of the build when told so", () => {
    expect(coverageText([first, last], true)).toBe(
      "This record covers only part of the build: from 1 March 2026 to 4 March 2026. Earlier work was archived and is not shown here.",
    );
    expect(coverageText([first, at("2026-03-01T18:00:00Z")], true)).toBe(
      "This record covers only part of the build: 1 March 2026. Earlier work was archived and is not shown here.",
    );
  });

  it("says nothing for an empty record or a line with no date", () => {
    expect(coverageText([], true)).toBeNull();
    expect(coverageText([at("later"), last], true)).toBeNull();
  });

  it("uses no word the page may not show", () => {
    const text = coverageText([first, last], true)!;
    expect(text).not.toMatch(/\b(hash|chain|ledger|entry|entries|seq|jsonl|sha-?256|canonical|hex)\b/i);
  });
});