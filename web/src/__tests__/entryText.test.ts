import { describe, expect, it } from "vitest";
import type { Entry } from "../lib/chainCheck";
import {
  entryText,
  evidenceRef,
  fingerprintText,
  overallSentence,
  undeclaredText,
  verdictSentence,
  verdictWord,
} from "../lib/entryText";

function entry(kind: string, data: Record<string, unknown>, seq = 1): Entry {
  return { seq, ts: "2026-01-01T00:00:00Z", session_id: "s", kind, data, prev_hash: "", hash: "" };
}

const tool = (name: string, input: Record<string, unknown>) =>
  entry("tool", { tool_name: name, tool_input: input });

describe("tool lines use plain verbs", () => {
  it.each([
    ["fs_write", { path: "docs/a.md" }, "Agent wrote docs/a.md."],
    ["str_replace", { path: "src/b.py" }, "Agent edited src/b.py."],
    ["read_file", { path: "src/c.py" }, "Agent read src/c.py."],
    ["something_else", {}, "Agent used a tool: something_else."],
  ])("%s", (name, input, expected) => {
    expect(entryText(tool(name, input))).toBe(expected);
  });

  it("describes a shell command and cuts it at 80 characters", () => {
    expect(entryText(tool("execute_pwsh", { command: "python sample/cleanup.py" }))).toBe(
      "Agent ran the command: python sample/cleanup.py.",
    );
    const long = entryText(tool("execute_pwsh", { command: "x".repeat(200) }));
    expect(long).toBe(`Agent ran the command: ${"x".repeat(80)}.`);
  });
});

describe("witness lines", () => {
  it("start", () => {
    expect(entryText(entry("witness", { event: "start" }))).toBe(
      "Witness took a snapshot of the project.",
    );
  });

  it("stop names the files, grouped, omitting empty groups", () => {
    const text = entryText(
      entry("witness", {
        event: "stop",
        diff: { created: ["a.md"], modified: [], deleted: ["x.txt", "y.bin"] },
      }),
    );
    expect(text).toBe(
      "Witness compared the project to the earlier snapshot. Created: a.md. Deleted: x.txt, y.bin.",
    );
    expect(text).not.toContain("Changed");
  });

  it("stop with no differences says so", () => {
    expect(
      entryText(entry("witness", { event: "stop", diff: { created: [], modified: [], deleted: [] } })),
    ).toBe("Witness compared the project to the earlier snapshot. No changes.");
  });
});


describe("verdict lines read as sentences", () => {
  const verdict = (claim: string, v: string, evidence: number[], path = "a.txt") =>
    entry("verdict", { path, claim, verdict: v, evidence_seq: evidence });

  it("supported: the witness agrees, and the line is cited", () => {
    expect(entryText(verdict("files_deleted", "SUPPORTED", [4]))).toBe(
      "Agent said it deleted a.txt. Witness agrees (line 4).",
    );
  });

  it("supported file read: it is the record that agrees, not the witness", () => {
    expect(entryText(verdict("files_read", "SUPPORTED", [2, 5], "src/m.py"))).toBe(
      "Agent said it read src/m.py. The record agrees (lines 2, 5).",
    );
  });

  it("contradicted: the witness says otherwise", () => {
    expect(entryText(verdict("files_created", "CONTRADICTED", [4], "new.py"))).toBe(
      "Agent said it created new.py. Witness says otherwise (line 4).",
    );
  });

  it("unverified: no evidence either way, and no line to cite", () => {
    expect(entryText(verdict("files_modified", "UNVERIFIED", [], "c.py"))).toBe(
      "Agent said it changed c.py. There is no evidence either way.",
    );
  });

  it("uses the right verb for each kind of claim", () => {
    const verb = (claim: string) =>
      verdictSentence({ claim, path: "p", verdict: "UNVERIFIED", evidence_seq: [] });
    expect(verb("files_created")).toContain("created p.");
    expect(verb("files_modified")).toContain("changed p.");
    expect(verb("files_deleted")).toContain("deleted p.");
    expect(verb("files_read")).toContain("read p.");
  });

  it("supported with no evidence line has no reference", () => {
    expect(entryText(verdict("files_deleted", "SUPPORTED", []))).toBe(
      "Agent said it deleted a.txt. Witness agrees.",
    );
  });

  it("none of them use the words the interface avoids", () => {
    const all = [
      verdict("files_deleted", "SUPPORTED", [4]),
      verdict("files_read", "SUPPORTED", [2]),
      verdict("files_created", "CONTRADICTED", [4]),
      verdict("files_modified", "UNVERIFIED", []),
    ].map(entryText);
    all.forEach((s) => expect(s).not.toMatch(/\b(hash|chain|ledger|entry|seq|sha|canonical|hex)\b/i));
  });
});

describe("the overall line", () => {
  const overall = (v: string) => entry("verdict", { kind_detail: "statement_overall", verdict: v });

  it("says whether the statement matches the evidence", () => {
    expect(overallSentence("SUPPORTED")).toBe("Overall: the statement matches the evidence.");
    expect(overallSentence("CONTRADICTED")).toBe("Overall: the statement does not match the evidence.");
    expect(overallSentence("UNVERIFIED")).toBe("Overall: some of the statement could not be checked.");
  });

  it("is what the overall record prints", () => {
    expect(entryText(overall("CONTRADICTED"))).toBe("Overall: the statement does not match the evidence.");
  });
});

describe("other lines", () => {
  it("evidence references", () => {
    expect(evidenceRef([2, 5])).toBe("(lines 2, 5)");
    expect(evidenceRef([7])).toBe("(line 7)");
    expect(evidenceRef([])).toBe("");
    expect(evidenceRef(undefined)).toBe("");
  });

  it("statement, undeclared change and errors", () => {
    expect(entryText(entry("statement", { summary: "Cleared the cache." }))).toBe(
      "Agent stated: Cleared the cache.",
    );
    expect(undeclaredText({ path: "sample/notes.txt", change: "deleted" })).toBe(
      "Witness saw sample/notes.txt deleted. The agent never mentioned it.",
    );
    expect(entryText(entry("error", { error: "disk full" }))).toBe("Something went wrong: disk full.");
  });
});


describe("a session with no statement", () => {
  it("says the agent changed files and said nothing", () => {
    expect(overallSentence("NO_STATEMENT")).toBe("Overall: the agent changed files and said nothing.");
  });
  it("prints NO_STATEMENT as two words and leaves other verdicts alone", () => {
    expect(verdictWord("NO_STATEMENT")).toBe("NO STATEMENT");
    expect(verdictWord("SUPPORTED")).toBe("SUPPORTED");
  });
});

describe("the fingerprint line", () => {
  it("names the last line's fingerprint and counts the lines", () => {
    expect(fingerprintText([])).toBe("Fingerprint of the record: none yet (0 lines)");
    expect(fingerprintText([{ hash: "ab" }])).toBe("Fingerprint of the record: ab (1 line)");
    expect(fingerprintText([{ hash: "ab" }, { hash: "cd" }])).toBe("Fingerprint of the record: cd (2 lines)");
  });
});
