// @vitest-environment node
import { describe, expect, it } from "vitest";
import fixture from "@@fixtures/sentences.json";
import type { Entry } from "../lib/chainCheck";
import { entryText, fingerprintText, verdictWord } from "../lib/entryText";

/*
  tests/fixtures/sentences.json is also read by tests/test_spool.py, so the
  screen and the print-ready text file print the same sentences.
*/

describe("the sentences shared with the print-ready text file", () => {
  it.each(fixture.sentences.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    const entry = { seq: 1, ts: "", session_id: "s", prev_hash: "", hash: "", ...c.entry } as unknown as Entry;
    expect(entryText(entry)).toBe(c.text);
  });

  it.each(fixture.verdictWords.map((c) => [c.verdict, c] as const))("verdict word for %s", (_v, c) => {
    expect(verdictWord(c.verdict)).toBe(c.word);
  });

  it.each(fixture.fingerprints.map((c) => [c.name, c] as const))("fingerprint: %s", (_name, c) => {
    expect(fingerprintText(c.entries)).toBe(c.text);
  });
});