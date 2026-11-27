import { useCallback, useEffect, useState } from "react";
import type { Entry } from "../lib/chainCheck";

export type Source = "loading" | "api" | "demo" | "error";

export const POLL_MS = 2000;

/** One JSON object per line; blank lines are ignored. */
export function parseJsonl(text: string): Entry[] {
  return text
    .split(/\r?\n/)
    .filter((line) => line.trim() !== "")
    .map((line) => JSON.parse(line) as Entry);
}

async function fetchApiEntries(): Promise<Entry[]> {
  const response = await fetch("/api/ledger");
  if (!response.ok) throw new Error(`API answered ${response.status}`);
  const data: unknown = await response.json(); // a page that is not JSON throws here
  if (!Array.isArray(data)) throw new Error("API did not return a list");
  return data as Entry[];
}

async function fetchDemoEntries(): Promise<Entry[]> {
  // Relative URL: works from any path the static site is served from.
  const response = await fetch("./demo/ledger.jsonl");
  if (!response.ok) throw new Error(`demo file answered ${response.status}`);
  return parseJsonl(await response.text());
}

/**
 * Loads the records: from the local API when it is running (then polls it),
 * otherwise from the static demo file (no polling).
 *
 * `original` is what was loaded. `tampered`, when set, is an in-memory copy
 * with one record changed. Polling only ever touches `original`, so a
 * tampered view is never overwritten; Restore simply drops the copy.
 */
export function useEntries(pollMs: number = POLL_MS) {
  const [original, setOriginal] = useState<Entry[]>([]);
  const [tampered, setTampered] = useState<Entry[] | null>(null);
  const [source, setSource] = useState<Source>("loading");

  // Initial load: API first, then the static demo.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await fetchApiEntries();
        if (!cancelled) {
          setOriginal(data);
          setSource("api");
        }
        return;
      } catch {
        // No API here (the normal case for the static site): use the demo.
      }
      try {
        const data = await fetchDemoEntries();
        if (!cancelled) {
          setOriginal(data);
          setSource("demo");
        }
      } catch {
        if (!cancelled) setSource("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Live mode only: pick up new records as they are written.
  useEffect(() => {
    if (source !== "api") return;
    const id = setInterval(() => {
      fetchApiEntries()
        .then((data) => setOriginal((prev) => (data.length > prev.length ? data : prev)))
        .catch(() => {
          /* the API went away for a moment; try again next time */
        });
    }, pollMs);
    return () => clearInterval(id);
  }, [source, pollMs]);

  /** Re-read the API now, for example right after a statement was checked. */
  const forceRefresh = useCallback(() => {
    if (source !== "api") return;
    fetchApiEntries()
      .then(setOriginal)
      .catch(() => {});
  }, [source]);

  /** Change one record in memory only. Nothing is written anywhere. */
  function tamper(seq: number): void {
    const base = tampered ?? original;
    setTampered(
      base.map((e) =>
        e.seq === seq ? { ...e, data: { ...e.data, _tampered: true } } : e,
      ),
    );
  }

  function restore(): void {
    setTampered(null);
  }

  return {
    entries: tampered ?? original,
    source,
    isTampered: tampered !== null,
    tamper,
    restore,
    forceRefresh,
  };
}
