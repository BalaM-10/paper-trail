// @vitest-environment node
import { describe, expect, it } from "vitest";
import { canonicalJson } from "../lib/canonicalJson";
import { checkChain, hashOf, type Entry } from "../lib/chainCheck";
import fixture from "@@fixtures/hash_fixture.json";
import demoLedgerRaw from "../../public/demo/ledger.jsonl?raw";

function demoEntries(): Entry[] {
  return demoLedgerRaw
    .split(/\r?\n/)
    .filter((line) => line.trim() !== "")
    .map((line) => JSON.parse(line) as Entry);
}

describe("canonical JSON matches Python", () => {
  it("hashes the fixture entry to the value Python computed", async () => {
    // Fixture covers quotes, backslash, newline, tab, U+0001, an emoji, an accent.
    const entry = { ...(fixture.entry as object), hash: "" } as Entry;
    expect(await hashOf(entry)).toBe(fixture.expected_hash);
  });

  it("sorts keys, uses no spaces, and keeps non-ASCII literal", () => {
    expect(canonicalJson({ b: 1, a: { d: [1, "é"], c: null } })).toBe(
      '{"a":{"c":null,"d":[1,"é"]},"b":1}',
    );
    expect(canonicalJson("🔍")).toBe('"🔍"');
  });

  it("escapes control characters the way Python does", () => {
    expect(canonicalJson("\u0001\t\n")).toBe('"\\u0001\\t\\n"');
  });
});

describe("the generated demo ledger", () => {
  it("is intact when checked in the browser implementation", async () => {
    const entries = demoEntries();
    expect(entries.length).toBeGreaterThan(10);
    expect(await checkChain(entries)).toEqual({ ok: true, count: entries.length });
  });
});

describe("tampering is detected at the first bad line", () => {
  it("catches changed data", async () => {
    const entries = demoEntries();
    entries[4] = { ...entries[4], data: { ...entries[4].data, _tampered: true } };
    expect(await checkChain(entries)).toMatchObject({ ok: false, brokenAt: entries[4].seq });
  });

  it("catches a changed hash", async () => {
    const entries = demoEntries();
    entries[6] = { ...entries[6], hash: "f".repeat(64) };
    expect(await checkChain(entries)).toMatchObject({ ok: false, brokenAt: entries[6].seq });
  });

  it("catches a missing line", async () => {
    const entries = demoEntries();
    const gap = entries.filter((e) => e.seq !== 3);
    expect(await checkChain(gap)).toMatchObject({ ok: false, brokenAt: 4 });
  });

  it("catches a broken link to the previous line", async () => {
    const entries = demoEntries();
    entries[2] = { ...entries[2], prev_hash: "0".repeat(64) };
    expect(await checkChain(entries)).toMatchObject({ ok: false, brokenAt: entries[2].seq });
  });

  it("treats an empty paper as intact", async () => {
    expect(await checkChain([])).toEqual({ ok: true, count: 0 });
  });
});
