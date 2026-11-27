// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { UndeclaredCircle } from "../components/UndeclaredCircle";

/*
  The red ring must leave room around the text at every width, and two rings on
  neighbouring lines must not touch.

  The ring is an SVG stretched over its button, so its real size comes from the
  stylesheets. This test reads those numbers, draws the ring's path into the same
  box, and checks it. Two things went wrong before and are checked by name:

  - the page rule `svg, img { max-width: 100% }` shrank the ring to the width of
    its button, so its right edge landed on the last word;
  - the ring stuck out further above and below than the gap between two buttons,
    so the rings of neighbouring lines overlapped.
*/

function css(name: string): string {
  return readFileSync(fileURLToPath(new URL(`../styles/${name}`, import.meta.url)), "utf8");
}
const stampsCss = css("stamps.css");
const paperCss = css("paper.css");

type Pt = [number, number];
type Layout = {
  padX: number;
  padY: number;
  /** Space above and below a button, in em. */
  marginY: number;
  left: number;
  top: number;
  extraW: number;
  extraH: number;
  /** Does the page cap the ring at the width of its button? */
  capped: boolean;
};

const LINE_HEIGHT = 1.35; // em, from .undeclared-circle
const MARGIN = 0.7; // em of air between the last word and the ring
const STROKE = 0.3; // em: the marker's widest stroke (3.2 px, 4.2 px on hover, at 15 px)
const NEIGHBOUR_GAP = 0.25; // em of clear paper between the strokes of two rings

function rules(source: string): [string, string][] {
  const clean = source.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...clean.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => [m[1].trim(), m[2]]);
}
function decl(body: string, name: string): string | undefined {
  return body.match(new RegExp(`(?:^|[;\\s])${name}\\s*:\\s*([^;]+)`))?.[1].trim();
}
function em(value: string | undefined): number {
  if (!value) throw new Error("missing value");
  return parseFloat(value);
}

/** Does any page rule for a plain `svg` cap its width at 100%? */
function pageCapsSvg(): boolean {
  return rules(paperCss).some(
    ([sel, body]) =>
      sel.split(",").map((s) => s.trim()).includes("svg") && /^100%$/.test(decl(body, "max-width") ?? ""),
  );
}

function layoutFrom(source: string, inheritedNone: boolean): Layout {
  const all = rules(source);
  const circle = all.find(([sel, body]) => sel === ".undeclared-circle" && decl(body, "padding"));
  const ring = all.find(([sel, body]) => sel === ".undeclared-circle__ring" && decl(body, "width"));
  if (!circle || !ring) throw new Error("ring rules not found");
  const [padY, padX] = decl(circle[1], "padding")!.split(/\s+/).map(em);
  const plus = (v: string | undefined) => em(v!.match(/\+\s*([\d.]+)em/)?.[1]);
  const none = (decl(ring[1], "max-width") ?? (inheritedNone ? "none" : "")) === "none";
  return {
    padX,
    padY,
    marginY: em(decl(circle[1], "margin")!.split(/\s+/)[0]),
    left: em(decl(ring[1], "left")),
    top: em(decl(ring[1], "top")),
    extraW: plus(decl(ring[1], "width")),
    extraH: plus(decl(ring[1], "height")),
    capped: pageCapsSvg() && !none,
  };
}

const base = layoutFrom(stampsCss, false);
const phoneMarker = "@media (max-width: 640px) {";
// The phone block only changes numbers; the ring keeps the base rule's max-width.
const phone = layoutFrom(stampsCss.slice(stampsCss.lastIndexOf(phoneMarker) + phoneMarker.length), !base.capped);

/** The ring's path, as rendered by the component. */
function ringPath(): string {
  const html = renderToStaticMarkup(createElement(UndeclaredCircle, { witnessSeq: 1, children: "x" }));
  const d = html.match(/<path d="([^"]+)"/)?.[1];
  if (!d) throw new Error("no path in the ring");
  return d;
}

/** Straight segments for a path made of one M and cubic C commands. */
function flatten(d: string): Pt[] {
  const nums = d.match(/-?[\d.]+/g)!.map(Number);
  const pts: Pt[] = [[nums[0], nums[1]]];
  for (let i = 2; i + 5 < nums.length; i += 6) {
    const [x0, y0] = pts[pts.length - 1];
    const [x1, y1, x2, y2, x3, y3] = nums.slice(i, i + 6);
    for (let s = 1; s <= 24; s++) {
      const t = s / 24;
      const u = 1 - t;
      pts.push([
        u * u * u * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t * t * t * x3,
        u * u * u * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t * t * t * y3,
      ]);
    }
  }
  return pts;
}

/**
 * Winding-number test. The loop's end overlaps its start, so a point between the
 * two passes is still enclosed by the outer stroke; an even-odd test would call
 * that thin overlap a hole.
 */
function inside(poly: Pt[], [x, y]: Pt): boolean {
  let winding = 0;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[j];
    const [xj, yj] = poly[i];
    const cross = (xj - xi) * (y - yi) - (x - xi) * (yj - yi);
    if (yi <= y && yj > y && cross > 0) winding++;
    else if (yi > y && yj <= y && cross < 0) winding--;
  }
  return winding !== 0;
}

/** Corners and edge midpoints of the text, grown by MARGIN, in em from the button's corner. */
function checkpoints(l: Layout, textW: number, lines: number): Pt[] {
  const x0 = l.padX - MARGIN;
  const x1 = l.padX + textW + MARGIN;
  const y0 = l.padY - MARGIN;
  const y1 = l.padY + lines * LINE_HEIGHT + MARGIN;
  const xm = (x0 + x1) / 2;
  const ym = (y0 + y1) / 2;
  return [[x0, y0], [x1, y0], [x0, y1], [x1, y1], [xm, y0], [xm, y1], [x0, ym], [x1, ym]];
}

/** Where the ring is, in em from the button's top-left corner, for text `textW` wide and `lines` tall. */
function ringPoints(d: string, l: Layout, textW: number, lines: number): Pt[] {
  const boxW = textW + 2 * l.padX;
  const boxH = lines * LINE_HEIGHT + 2 * l.padY;
  const declaredW = boxW + l.extraW;
  const ringW = l.capped ? Math.min(declaredW, boxW) : declaredW; // max-width: 100% of the button
  const ringH = boxH + l.extraH;
  // The path lives in a 100 x 40 box that is stretched over the ring's box.
  return flatten(d).map(([px, py]) => [l.left + (px / 100) * ringW, l.top + (py / 40) * ringH] as Pt);
}

/** Which checkpoints the ring does NOT enclose. */
function missed(d: string, l: Layout, textW: number, lines: number): Pt[] {
  const poly = ringPoints(d, l, textW, lines);
  return checkpoints(l, textW, lines).filter((p) => !inside(poly, p));
}

/**
 * Clear paper, in em, between the strokes of a ring and the ring of the button
 * below it (two buttons are 2 x marginY apart, because each has its own margin).
 */
function neighbourGap(d: string, above: Layout, linesAbove: number, below: Layout, linesBelow: number): number {
  const widths = 20;
  const bottomOfFirst = Math.max(...ringPoints(d, above, widths, linesAbove).map(([, y]) => y));
  const boxHeightAbove = linesAbove * LINE_HEIGHT + 2 * above.padY;
  const belowStart = boxHeightAbove + above.marginY + below.marginY;
  const topOfSecond = Math.min(...ringPoints(d, below, widths, linesBelow).map(([, y]) => y)) + belowStart;
  return topOfSecond - bottomOfFirst - STROKE;
}

const WIDTHS = [8, 12, 20, 33, 47, 60];
/** A 375 px phone is about 23 em wide at 16 px, and the line has its own padding. */
const PHONE_WIDTHS = [8, 12, 16, 20];
const LINES = [1, 2, 3, 4];

describe("the red ring leaves room around its text", () => {
  const d = ringPath();

  it("reads sensible numbers from the stylesheets", () => {
    expect(base.padX).toBeGreaterThan(0);
    expect(phone.padX).toBeGreaterThan(0);
    expect(base.extraW).toBeGreaterThan(0);
    expect(phone.extraH).toBeGreaterThan(0);
    expect(base.marginY).toBeGreaterThan(0);
  });

  for (const [name, layout] of [["desktop", base], ["phone", phone]] as const) {
    it(`encloses the text on ${name}, for every width and number of lines`, () => {
      for (const w of layout === phone ? PHONE_WIDTHS : WIDTHS) {
        for (const n of LINES) {
          expect(missed(d, layout, w, n), `${name}: ${w}em wide, ${n} line(s)`).toEqual([]);
        }
      }
    });
  }

  it("is not shrunk by the page's rule for svg images (the cause of the right edge on the last word)", () => {
    expect(pageCapsSvg(), "this test only means something while the page caps svg").toBe(true);
    expect(base.capped).toBe(false);
    expect(phone.capped).toBe(false);
    expect(/\.undeclared-circle__ring\s*\{[^}]*max-width:\s*none/.test(stampsCss)).toBe(true);
  });

  it("would catch that cap: with it, the longest line has the ring's edge on the text", () => {
    const longest = 60;
    const withCap = { ...base, capped: true };
    const gone = missed(d, withCap, longest, 1);
    expect(gone.length).toBeGreaterThan(0);
    // the right-hand checkpoints are among those left outside
    const rightEdge = base.padX + longest + MARGIN;
    expect(gone.some(([x]) => Math.abs(x - rightEdge) < 1e-9)).toBe(true);
  });

  it("catches the old tight ellipse with its old offsets (the test can fail)", () => {
    const oldEllipse =
      "M 14 9 C 30 2, 70 1, 88 7 C 99 12, 99 28, 86 33 C 68 40, 30 39, 13 32 C 2 27, 1 13, 14 8 C 20 5, 30 3, 40 3";
    const tight: Layout = { ...base, padX: 0.5, padY: 0.2, left: 0, top: 0, extraW: 0, extraH: 0 };
    const failures = WIDTHS.flatMap((w) => LINES.map((n) => missed(oldEllipse, tight, w, n).length));
    expect(failures.some((count) => count > 0)).toBe(true);
  });
});

describe("rings on neighbouring lines stay apart", () => {
  const d = ringPath();

  for (const [name, layout] of [["desktop", base], ["phone", phone]] as const) {
    it(`leaves clear paper between two rings on ${name}, for every mix of 1 to 4 lines`, () => {
      for (const a of LINES) {
        for (const b of LINES) {
          const gap = neighbourGap(d, layout, a, layout, b);
          expect(gap, `${name}: ${a} line(s) above ${b} line(s): ${gap.toFixed(2)} em`).toBeGreaterThanOrEqual(
            NEIGHBOUR_GAP,
          );
        }
      }
    });
  }

  it("would catch the old spacing: rings 1 em tall beyond a button, buttons 0.6 em apart", () => {
    const old: Layout = { ...base, marginY: 0.3, top: -1, extraH: 2 };
    const gaps = LINES.flatMap((a) => LINES.map((b) => neighbourGap(d, old, a, old, b)));
    expect(gaps.every((g) => g < 0)).toBe(true); // they overlapped
  });

  it("keeps the ring hand-drawn: an uneven loop whose end overshoots its start", () => {
    const pts = flatten(d);
    const [first, last] = [pts[0], pts[pts.length - 1]];
    expect(Math.hypot(first[0] - last[0], first[1] - last[1])).toBeGreaterThan(5); // not closed neatly
    // the end has gone past the start along the path: it lies inside the loop, on the top-left
    expect(last[0]).toBeGreaterThan(first[0]);
    // not a plain rectangle: the curve commands are all cubic and there are many of them
    expect((d.match(/C/g) ?? []).length).toBeGreaterThanOrEqual(8);
    // it uses the marker filter
    expect(stampsCss).toMatch(/\.undeclared-circle__ring path\s*\{[^}]*filter:\s*url\(#marker-ink\)/);
  });
});
