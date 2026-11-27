import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SPEEDS, useReplay } from "../hooks/useReplay";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

type Props = { total: number; key: string | null; follow: boolean };

function setup(initial: Props) {
  return renderHook((p: Props) => useReplay(p.total, p.key, p.follow), { initialProps: initial });
}

/** One interval per act(): React only re-renders (and schedules the next line) when act ends. */
const tick = (ms: number) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });

async function ticks(count: number, ms: number) {
  for (let i = 0; i < count; i++) await tick(ms);
}

describe("manual stepping", () => {
  it("starts idle and hidden", () => {
    const { result } = setup({ total: 3, key: "a", follow: false });
    expect(result.current.state).toBe("idle");
    expect(result.current.cursor).toBe(0);
  });

  it("advances exactly one line per Step, pausing between", () => {
    const { result } = setup({ total: 3, key: "a", follow: false });
    act(() => result.current.step());
    expect([result.current.state, result.current.cursor]).toEqual(["paused", 1]);
    act(() => result.current.step());
    expect([result.current.state, result.current.cursor]).toEqual(["paused", 2]);
    act(() => result.current.step());
    expect([result.current.state, result.current.cursor]).toEqual(["done", 3]);
  });

  it("does nothing with no lines", () => {
    const { result } = setup({ total: 0, key: null, follow: false });
    act(() => result.current.step());
    act(() => result.current.play());
    expect(result.current.state).toBe("idle");
  });
});

describe("play and pause", () => {
  it("prints one line per interval at the chosen speed", async () => {
    const { result } = setup({ total: 3, key: "a", follow: false });
    act(() => result.current.setSpeed(SPEEDS.fast));
    act(() => result.current.play());
    await tick(99);
    expect(result.current.cursor).toBe(0);
    await tick(1);
    expect(result.current.cursor).toBe(1);
    await ticks(2, 100);
    expect(result.current.cursor).toBe(3);
    expect(result.current.state).toBe("done");
  });

  it("offers the three speeds", () => {
    expect(SPEEDS).toEqual({ slow: 1000, normal: 400, fast: 100 });
  });

  it("pause holds the current line", async () => {
    const { result } = setup({ total: 5, key: "a", follow: false });
    act(() => result.current.play());
    await ticks(2, 400);
    expect(result.current.cursor).toBe(2);
    act(() => result.current.pause());
    await tick(5000);
    expect(result.current.cursor).toBe(2);
    expect(result.current.state).toBe("paused");
  });

  it("playing a finished replay starts again from the top", async () => {
    const { result } = setup({ total: 2, key: "a", follow: false });
    act(() => result.current.step());
    act(() => result.current.step());
    expect(result.current.state).toBe("done");
    act(() => result.current.play());
    expect([result.current.state, result.current.cursor]).toEqual(["playing", 0]);
    await tick(400);
    expect(result.current.cursor).toBe(1);
  });
});

describe("a different session", () => {
  it("starts again from the top", () => {
    const { result, rerender } = setup({ total: 3, key: "a", follow: false });
    act(() => result.current.step());
    act(() => result.current.step());
    rerender({ total: 4, key: "b", follow: false });
    expect([result.current.state, result.current.cursor]).toEqual(["idle", 0]);
  });
});

describe("new lines arriving live", () => {
  it("keeps the position when lines are added mid-replay", () => {
    const { result, rerender } = setup({ total: 3, key: "a", follow: true });
    act(() => result.current.step());
    act(() => result.current.step());
    rerender({ total: 6, key: "a", follow: true });
    expect([result.current.state, result.current.cursor]).toEqual(["paused", 2]);
  });

  it("prints new lines by itself when the replay had reached the end (live)", async () => {
    const { result, rerender } = setup({ total: 2, key: "a", follow: true });
    act(() => result.current.step());
    act(() => result.current.step());
    expect(result.current.state).toBe("done");

    rerender({ total: 4, key: "a", follow: true });
    expect(result.current.state).toBe("playing");
    expect(result.current.cursor).toBe(2); // not reset
    await ticks(2, 400);
    expect([result.current.state, result.current.cursor]).toEqual(["done", 4]);
  });

  it("waits for Play when not following", () => {
    const { result, rerender } = setup({ total: 2, key: "a", follow: false });
    act(() => result.current.step());
    act(() => result.current.step());
    rerender({ total: 4, key: "a", follow: false });
    expect([result.current.state, result.current.cursor]).toEqual(["paused", 2]);
  });

  it("does not move when the same number of lines are replaced (tamper/restore)", () => {
    const { result, rerender } = setup({ total: 3, key: "a", follow: true });
    act(() => result.current.step());
    rerender({ total: 3, key: "a", follow: true });
    expect([result.current.state, result.current.cursor]).toEqual(["paused", 1]);
  });
});


describe("skip to end", () => {
  it("prints everything at once and finishes", () => {
    const { result } = setup({ total: 2000, key: "a", follow: false });
    act(() => result.current.step());
    act(() => result.current.skipToEnd());
    expect([result.current.state, result.current.cursor]).toEqual(["done", 2000]);
  });

  it("works while playing, and stops the playing", async () => {
    const { result } = setup({ total: 50, key: "a", follow: false });
    act(() => result.current.play());
    await tick(SPEEDS.normal);
    act(() => result.current.skipToEnd());
    expect([result.current.state, result.current.cursor]).toEqual(["done", 50]);
    await ticks(3, SPEEDS.normal);
    expect(result.current.cursor).toBe(50);
  });

  it("does nothing when there is nothing to print", () => {
    const { result } = setup({ total: 0, key: "a", follow: false });
    act(() => result.current.skipToEnd());
    expect([result.current.state, result.current.cursor]).toEqual(["idle", 0]);
  });

  it("lets PLAY start again from the top, as it does at the end of a replay", () => {
    const { result } = setup({ total: 5, key: "a", follow: false });
    act(() => result.current.skipToEnd());
    act(() => result.current.play());
    expect([result.current.state, result.current.cursor]).toEqual(["playing", 0]);
  });
});