// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { UndeclaredCircle } from "../components/UndeclaredCircle";

/*
  The red ring must leave room around the text at every width. The ring is an
  SVG stretched over the button, so its real size comes from stamps.css. This
  test reads those numbers, draws the ring's path into the same box, and checks
  that the corners and edge midpoints of the text (plus a margin) are inside it.
*/

const stampsCss = readFileSync(fileURLToPath(new URL("../styles/stamps.css", import.meta.url)), "utf8");

type Pt = [number, number];
type Layout = { padX: number; padY: number; left: number; top: number; extraW: number; extraH: number };

const LINE_HEIGHT = 1.35; // em, from .undeclared-circle
const MARGIN = 0.7; // em of air between the last word and the ring

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
function layoutFrom(source: string): Layout {
  const all = rules(source);
  const circle = all.find(([sel, body]) => sel === ".undeclared-circle" && decl(body, "padding"));
  const ring = all.find(([sel, body]) => sel === ".undeclared-circle__ring" && decl(body, "width"));
  if (!circle || !ring) throw new Error("ring rules not found");
  const [padY, padX] = decl(circle[1], "padding")!.split(/\s+/).map(em);
  const plus = (v: string | undefined) => em(v!.match(/\+\s*([\d.]+)em/)?.[1]);
  return {
    padX,
    padY,
    left: em(decl(ring[1], "left")),
    top: em(decl(ring[1], "top")),
    extraW: plus(decl(ring[1], "width")),
    extraH: plus(decl(ring[1], "height")),
  };
}

const base = layoutFrom(stampsCss);
const phoneMarker = "@media (max-width: 640px) {";
const phone = layoutFrom(stampsCss.slice(stampsCss.lastIndexOf(phoneMarker) + phoneMarker.length));

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
  for (let i = 2; i + 5 < nums.length + 0; i += 6) {
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

/** Which checkpoints the ring does NOT enclose. */
function missed(d: string, l: Layout, textW: number, lines: number): Pt[] {
  const poly = flatten(d);
  const boxW = textW + 2 * l.padX;
  const boxH = lines * LINE_HEIGHT + 2 * l.padY;
  const ringW = boxW + l.extraW;
  const ringH = boxH + l.extraH;
  // The path lives in a 100 x 40 box that is stretched over the ring's box.
  const toEm = ([px, py]: Pt): Pt => [l.left + (px / 100) * ringW, l.top + (py / 40) * ringH];
  const inEm = poly.map(toEm);
  return checkpoints(l, textW, lines).filter((p) => !inside(inEm, p));
}

/** The paper is about 54 em wide at 16 px, so a line of text never passes 60 em. */
const WIDTHS = [8, 12, 20, 33, 47, 60];
/** A 375 px phone is about 23 em wide at 16 px, and the line has its own padding. */
const PHONE_WIDTHS = [8, 12, 16, 20];
const LINES = [1, 2, 3, 4];

describe("the red ring leaves room around its text", () => {
  const d = ringPath();

  it("reads sensible numbers from the stylesheet", () => {
    expect(base.padX).toBeGreaterThan(0);
    expect(phone.padX).toBeGreaterThan(0);
    expect(base.extraW).toBeGreaterThan(0);
    expect(phone.extraH).toBeGreaterThan(0);
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

  it("catches the old tight ellipse with its old offsets (the test can fail)", () => {
    const oldEllipse =
      "M 14 9 C 30 2, 70 1, 88 7 C 99 12, 99 28, 86 33 C 68 40, 30 39, 13 32 C 2 27, 1 13, 14 8 C 20 5, 30 3, 40 3";
    const tight: Layout = { padX: 0.5, padY: 0.2, left: 0, top: 0, extraW: 0, extraH: 0 };
    const failures = WIDTHS.flatMap((w) => LINES.map((n) => missed(oldEllipse, tight, w, n).length));
    expect(failures.some((count) => count > 0)).toBe(true);
  });
});
