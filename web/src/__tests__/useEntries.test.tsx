import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useEntries } from "../hooks/useEntries";
import type { Entry } from "../lib/chainCheck";
import { demoEntries, demoText } from "./demo";

/** A response-shaped object, so fake timers cannot stall a real body stream. */
function fake(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => (typeof body === "string" ? body : JSON.stringify(body)),
  } as unknown as Response;
}

let ledgerCalls: number;
let served: Entry[];
let apiUp: boolean;
let buildText: string | null;

beforeEach(() => {
  vi.useFakeTimers();
  ledgerCalls = 0;
  served = demoEntries.slice(0, 8);
  apiUp = true;
  buildText = null;
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/ledger") {
      ledgerCalls += 1;
      if (!apiUp) throw new TypeError("no server");
      return fake(served);
    }
    if (url === "./demo/ledger.jsonl") return fake(demoText);
    if (url === "./demo/build-ledger.jsonl") return buildText === null ? fake("Not found", 404) : fake(buildText);
    throw new TypeError("unexpected " + url);
  });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function settle(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("loading", () => {
  it("uses the API when it answers", async () => {
    const { result } = renderHook(() => useEntries(2000));
    await settle();
    expect(result.current.source).toBe("api");
    expect(result.current.entries).toHaveLength(8);
  });

  it("falls back to the static demo ledger, and then never polls", async () => {
    apiUp = false;
    const { result } = renderHook(() => useEntries(2000));
    await settle();
    expect(result.current.source).toBe("demo");
    expect(result.current.entries).toHaveLength(demoEntries.length);

    const callsAfterLoad = ledgerCalls;
    await settle(20_000);
    expect(ledgerCalls).toBe(callsAfterLoad);
  });

  it("reports an error when neither source works", async () => {
    apiUp = false;
    vi.mocked(globalThis.fetch).mockImplementation(async () => {
      throw new TypeError("offline");
    });
    const { result } = renderHook(() => useEntries(2000));
    await settle();
    expect(result.current.source).toBe("error");
  });
});

describe("live polling", () => {
  it("asks again every 2 seconds and picks up new records", async () => {
    const { result } = renderHook(() => useEntries(2000));
    await settle();
    const first = ledgerCalls;

    served = demoEntries.slice(0, 11);
    await settle(1999);
    expect(ledgerCalls).toBe(first);
    expect(result.current.entries).toHaveLength(8);

    await settle(1);
    expect(ledgerCalls).toBe(first + 1);
    expect(result.current.entries).toHaveLength(11);
  });

  it("keeps polling quietly when the API drops out for a moment", async () => {
    const { result } = renderHook(() => useEntries(2000));
    await settle();
    apiUp = false;
    await settle(4000);
    expect(result.current.entries).toHaveLength(8);
    expect(result.current.source).toBe("api");
    apiUp = true;
    served = demoEntries.slice(0, 10);
    await settle(2000);
    expect(result.current.entries).toHaveLength(10);
  });

  it("never overwrites a tampered view, and Restore then shows the newest records", async () => {
    const { result } = renderHook(() => useEntries(2000));
    await settle();

    act(() => result.current.tamper(3));
    expect(result.current.isTampered).toBe(true);
    const tamperedView = result.current.entries;
    expect(tamperedView.find((e) => e.seq === 3)!.data._tampered).toBe(true);

    served = demoEntries.slice(0, 12); // new records arrive while tampered
    await settle(2000);
    expect(result.current.entries).toBe(tamperedView); // untouched
    expect(result.current.entries).toHaveLength(8);

    act(() => result.current.restore());
    expect(result.current.isTampered).toBe(false);
    expect(result.current.entries).toHaveLength(12);
    expect(result.current.entries.find((e) => e.seq === 3)!.data._tampered).toBeUndefined();
  });

  it("tampers in memory only: the loaded records are not changed", async () => {
    const { result } = renderHook(() => useEntries(2000));
    await settle();
    const before = result.current.entries;
    act(() => result.current.tamper(2));
    expect(before.find((e) => e.seq === 2)!.data._tampered).toBeUndefined();
  });

  it("forceRefresh re-reads at once", async () => {
    const { result } = renderHook(() => useEntries(60_000));
    await settle();
    served = demoEntries;
    await act(async () => {
      result.current.forceRefresh();
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.entries).toHaveLength(demoEntries.length);
  });
});


describe("the build record", () => {
  it("loads the build file, never calls the API and never polls", async () => {
    buildText = demoText; // any well-formed record will do here
    const { result } = renderHook(() => useEntries(2000, "build"));
    await settle();
    expect(result.current.source).toBe("build");
    expect(result.current.entries).toHaveLength(demoEntries.length);
    expect(ledgerCalls).toBe(0);
    await settle(20_000);
    expect(ledgerCalls).toBe(0);
  });

  it.each([
    ["a missing file", null],
    ["a page that is not a record", "<!doctype html><html></html>"],
    ["an empty file", ""],
    ["lines that are not records", '{"hello": 1}\n'],
  ])("reports %s as build-missing, not as an error", async (_name, text) => {
    buildText = text;
    const { result } = renderHook(() => useEntries(2000, "build"));
    await settle();
    expect(result.current.source).toBe("build-missing");
    expect(result.current.entries).toHaveLength(0);
  });

  it("starts again when the view changes: nothing loaded, nothing tampered", async () => {
    buildText = demoText;
    const { result, rerender } = renderHook(({ view }) => useEntries(2000, view), {
      initialProps: { view: "demo" as "demo" | "build" },
    });
    await settle();
    expect(result.current.source).toBe("api");
    act(() => result.current.tamper(3));
    expect(result.current.isTampered).toBe(true);

    rerender({ view: "build" });
    await settle();
    expect(result.current.source).toBe("build");
    expect(result.current.isTampered).toBe(false);
    expect(result.current.entries.some((e) => e.data._tampered)).toBe(false);

    rerender({ view: "demo" });
    await settle();
    expect(result.current.source).toBe("api");
  });

  it("ignores a slow answer for a view that is no longer shown", async () => {
    buildText = demoText;
    const { result, rerender } = renderHook(({ view }) => useEntries(2000, view), {
      initialProps: { view: "build" as "demo" | "build" },
    });
    rerender({ view: "demo" }); // before the build file has answered
    await settle();
    expect(result.current.source).toBe("api");
  });
});
