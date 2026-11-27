import { describe, expect, it } from "vitest";
import { MIN_INK, inkFor } from "../lib/ink";

describe("ink density", () => {
  it("is always between the faintest ink and full black", () => {
    for (let seq = -50; seq <= 500; seq++) {
      const d = inkFor(seq);
      expect(d).toBeGreaterThanOrEqual(MIN_INK);
      expect(d).toBeLessThanOrEqual(1);
    }
  });

  it("is the same for the same line, so the paper never shimmers", () => {
    for (const seq of [1, 9, 14, 200]) expect(inkFor(seq)).toBe(inkFor(seq));
  });

  it("differs between neighbouring lines and over a run of lines", () => {
    for (let seq = 1; seq < 100; seq++) expect(inkFor(seq)).not.toBe(inkFor(seq + 1));
    const run = new Set(Array.from({ length: 40 }, (_, i) => inkFor(i + 1)));
    expect(run.size).toBeGreaterThanOrEqual(15);
  });

  it("copes with odd input", () => {
    expect(inkFor(Number.NaN)).toBeGreaterThanOrEqual(MIN_INK);
    expect(inkFor(Number.POSITIVE_INFINITY)).toBeLessThanOrEqual(1);
    expect(inkFor(-7)).toBe(inkFor(7));
    expect(inkFor(3.9)).toBe(inkFor(3));
  });

  it("has a faintest ink of 0.82", () => {
    expect(MIN_INK).toBe(0.82);
    expect(Math.min(...Array.from({ length: 19 }, (_, i) => inkFor(i)))).toBe(0.82);
    expect(Math.max(...Array.from({ length: 19 }, (_, i) => inkFor(i)))).toBe(1);
  });
});
