import { canonicalJson } from "./canonicalJson";

/** One record of the paper, exactly as stored. */
export type Entry = {
  seq: number;
  ts: string;
  session_id: string;
  kind: string;
  data: Record<string, unknown>;
  prev_hash: string;
  hash: string;
};

export type ChainResult =
  | { ok: true; count: number }
  | { ok: false; brokenAt: number; count: number };

const ZERO_HASH = "0".repeat(64);

async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** The hash a record should carry: SHA-256 of its canonical JSON without `hash`. */
export async function hashOf(entry: Entry): Promise<string> {
  const { hash: _ignored, ...withoutHash } = entry;
  return sha256Hex(canonicalJson(withoutHash));
}

/**
 * Walk the records in order. The first record whose number, link to the
 * previous record, or own hash is wrong is where the paper is torn.
 */
export async function checkChain(entries: Entry[]): Promise<ChainResult> {
  let expectedPrev = ZERO_HASH;
  let expectedSeq = 1;
  for (const entry of entries) {
    if (
      entry.seq !== expectedSeq ||
      entry.prev_hash !== expectedPrev ||
      (await hashOf(entry)) !== entry.hash
    ) {
      return { ok: false, brokenAt: entry.seq, count: entries.length };
    }
    expectedPrev = entry.hash;
    expectedSeq += 1;
  }
  return { ok: true, count: entries.length };
}
