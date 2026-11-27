import { hashOf, type Entry } from "../lib/chainCheck";
import { ok } from "./demo";

/*
  Records for tests: a real hash chain, built the way the recorder builds it,
  so the page's own check accepts it. Nothing here is the project's real record.
*/

const ZERO = "0".repeat(64);

export type Outcome = "supported" | "contradicted" | "silent" | "unchecked" | "plain";

export type SessionSpec = {
  id: string;
  /** How many tool lines between the two snapshots. */
  tools: number;
  outcome: Outcome;
  summary?: string;
  /** "turn": the recording setup changed in the turn. "between": a between-turns line says it changed. */
  setup?: "turn" | "between";
};

type Row = { session: string; kind: string; data: Record<string, unknown> };

function rowsFor(spec: SessionSpec): Row[] {
  const { id, tools, outcome } = spec;
  const rows: Row[] = [{ session: id, kind: "witness", data: { event: "start", snapshot: {} } }];
  for (let i = 0; i < tools; i++) {
    rows.push({
      session: id,
      kind: "tool",
      data: { tool_name: "read_file", tool_input: { path: `src/file${i}.py` } },
    });
  }
  const created = outcome === "silent" ? ["src/new.py"] : [];
  const deleted = outcome === "contradicted" ? ["build/a.bin", "notes.txt"] : [];
  if (spec.setup === "between") {
    rows.push({
      session: id,
      kind: "witness",
      data: {
        event: "between_turns",
        diff: { created: [], modified: [".kiro/hooks/record.py"], deleted: [] },
        unfinished: false,
        setup_changed: [".kiro/hooks/record.py"],
      },
    });
  }
  rows.push({
    session: id,
    kind: "witness",
    data: { event: "stop", diff: { created, modified: [], deleted } },
  });
  if (spec.setup === "turn") {
    rows.push({
      session: id,
      kind: "witness",
      data: { event: "setup_changed", files: [".kiro/hooks/record.py"] },
    });
  }
  return rows;
}

/** Builds the records for the sessions, in order, as parsed entries and as file text. */
export async function makeRecord(specs: SessionSpec[]): Promise<{ entries: Entry[]; text: string }> {
  const entries: Entry[] = [];
  let prev = ZERO;
  let seq = 0;
  let clock = Date.parse("2026-03-01T09:00:00Z");

  async function add(session: string, kind: string, data: Record<string, unknown>): Promise<number> {
    seq += 1;
    clock += 1000;
    const entry: Entry = {
      seq,
      ts: new Date(clock).toISOString(),
      session_id: session,
      kind,
      data,
      prev_hash: prev,
      hash: "",
    };
    entry.hash = await hashOf(entry);
    prev = entry.hash;
    entries.push(entry);
    return seq;
  }

  for (const spec of specs) {
    const rows = rowsFor(spec);
    let stopSeq = 0;
    for (const row of rows) {
      const n = await add(row.session, row.kind, row.data);
      if (row.kind === "witness" && row.data.event === "stop") stopSeq = n;
    }
    const summary = spec.summary ?? `Work in ${spec.id}.`;
    if (spec.outcome === "plain") continue;
    if (spec.outcome === "silent") {
      await add(spec.id, "verdict", {
        kind_detail: "statement_overall",
        verdict: "NO_STATEMENT",
        evidence_seq: [stopSeq],
        witness_seq: stopSeq,
        undeclared: [{ path: "src/new.py", change: "created" }],
      });
      continue;
    }
    await add(spec.id, "statement", {
      summary,
      files_read: [],
      files_created: [],
      files_modified: [],
      files_deleted: spec.outcome === "contradicted" ? ["build/a.bin"] : [],
      session_id: spec.id,
      witness_seq: stopSeq,
    });
    if (spec.outcome === "unchecked") continue;
    if (spec.outcome === "contradicted") {
      await add(spec.id, "verdict", {
        path: "build/a.bin",
        claim: "files_deleted",
        verdict: "SUPPORTED",
        evidence_seq: [stopSeq],
        witness_seq: stopSeq,
      });
    }
    await add(spec.id, "verdict", {
      kind_detail: "statement_overall",
      verdict: spec.outcome === "supported" ? "SUPPORTED" : "CONTRADICTED",
      evidence_seq: [stopSeq],
      witness_seq: stopSeq,
      undeclared: spec.outcome === "contradicted" ? [{ path: "notes.txt", change: "deleted" }] : [],
    });
  }
  return { entries, text: entries.map((e) => JSON.stringify(e)).join("\n") + "\n" };
}

/** Answers like the static site: no API, the demo file, and (if given) the build record. */
export function staticSite(
  demoText: string,
  buildText: string | null,
  metaText: string | null = null,
): (input: RequestInfo | URL) => Promise<Response> {
  return async (input) => {
    const url = String(input);
    if (url.includes("/api/")) throw new TypeError("no server");
    if (url.includes("build-record.json")) {
      return metaText === null ? new Response("Not found", { status: 404 }) : ok(metaText);
    }
    if (url.includes("build-ledger.jsonl")) {
      return buildText === null ? new Response("Not found", { status: 404 }) : ok(buildText);
    }
    return ok(demoText);
  };
}
