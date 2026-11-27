import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useFreshLine } from "../hooks/useFreshLine";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

type Props = { cursor: number; torn: boolean };
const setup = (initial: Props = { cursor: 0, torn: false }) =>
  renderHook((p: Props) => useFreshLine(p.cursor, p.torn), { initialProps: initial });

describe("the line that has just printed", () => {
  it("is none until something prints", () => {
    expect(setup().result.current).toBe(-1);
  });

  it("is the last line printed, and moves on with the print head", () => {
    const { result, rerender } = setup();
    rerender({ cursor: 1, torn: false });
    expect(result.current).toBe(0);
    rerender({ cursor: 2, torn: false });
    expect(result.current).toBe(1);
  });

  it("is gone once its animation has finished", () => {
    const { result, rerender } = setup();
    rerender({ cursor: 3, torn: false });
    expect(result.current).toBe(2);
    act(() => {
      vi.advanceTimersByTime(1199);
    });
    expect(result.current).toBe(2);
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(result.current).toBe(-1);
  });

  it("is none again when the replay goes back to the start", () => {
    const { result, rerender } = setup({ cursor: 4, torn: false });
    rerender({ cursor: 0, torn: false });
    expect(result.current).toBe(-1);
  });
});

describe("tearing and mending the paper", () => {
  it("never marks a line fresh in the very render where the paper tears", () => {
    const { result, rerender } = setup();
    rerender({ cursor: 5, torn: false });
    expect(result.current).toBe(4);

    // lines are rebuilt in this render: none may carry the animation
    rerender({ cursor: 5, torn: true });
    expect(result.current).toBe(-1);
    // and it stays that way afterwards
    rerender({ cursor: 5, torn: true });
    expect(result.current).toBe(-1);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    expect(result.current).toBe(-1);
  });

  it("is the same when the paper is mended", () => {
    const { result, rerender } = setup({ cursor: 5, torn: true });
    rerender({ cursor: 5, torn: false });
    expect(result.current).toBe(-1);
    rerender({ cursor: 5, torn: false });
    expect(result.current).toBe(-1);
  });

  it("lets the next printed line animate normally after a tear", () => {
    const { result, rerender } = setup({ cursor: 2, torn: false });
    rerender({ cursor: 2, torn: true });
    rerender({ cursor: 3, torn: true });
    expect(result.current).toBe(2);
  });
});
