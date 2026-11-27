import { useCallback, useEffect, useState } from "react";
import type { Entry } from "../lib/chainCheck";

/** Where the records came from. "build" is the record of how Paper Trail was built. */
export type Source = "loading" | "api" | "demo" | "build" | "build-missing" | "error";
/** Which record to show: the demo (or the live one), or the build record. */
export type View = "demo" | "build";
const EMPTY: Entry[] = [];

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

async function fetchBuildEntries(): Promise<Entry[]> {
  const response = await fetch("./demo/build-ledger.jsonl");
  if (!response.ok) throw new Error(`build record answered ${response.status}`);
  const entries = parseJsonl(await response.text()); // a page that is not records throws here
  const sane = entries.every((e) => typeof e.seq === "number" && typeof e.hash === "string" && e.data !== undefined);
  if (entries.length === 0 || !sane) throw new Error("not a record");
  return entries;
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
 * With `view` "build" it loads the build record instead, never calls the API and
 * never polls. A missing or unreadable file gives the source "build-missing".
 * Changing `view` starts again: nothing loaded, nothing tampered.
 *
 * `original` is what was loaded. `tampered`, when set, is an in-memory copy
 * with one record changed. Polling only ever touches `original`, so a
 * tampered view is never overwritten; Restore simply drops the copy.
 */
export function useEntries(pollMs: number = POLL_MS, view: View = "demo") {
  const [original, setOriginal] = useState<Entry[]>(EMPTY);
  const [tampered, setTampered] = useState<Entry[] | null>(null);
  const [source, setSource] = useState<Source>("loading");

  // Initial load: API first, then the static demo. (Or the build record.)
  useEffect(() => {
    let cancelled = false;
    setOriginal(EMPTY);
    setTampered(null);
    setSource("loading");
    (async () => {
      if (view === "build") {
        try {
          const data = await fetchBuildEntries();
          if (!cancelled) {
            setOriginal(data);
            setSource("build");
          }
        } catch {
          if (!cancelled) setSource("build-missing");
        }
        return;
      }
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
  }, [view]);

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
