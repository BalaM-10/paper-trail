// @vitest-environment node
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { MIN_INK } from "../lib/ink";

// Read from disk: Vitest swaps CSS imports (even ?raw) for an empty string.
function css(name: string): string {
  return readFileSync(fileURLToPath(new URL(`../styles/${name}`, import.meta.url)), "utf8");
}
const paperCss = css("paper.css");
const printCss = css("print.css");
const stampsCss = css("stamps.css");

/* ---- a tiny stylesheet reader ------------------------------------------- */

/** Every innermost rule as [selector, declarations], in file order (media context is dropped). */
function allRules(source: string): [string, string][] {
  const clean = source.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...clean.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => [m[1].trim(), m[2]]);
}

/** Declaration blocks of rules whose selector list contains `selector`. */
function blocks(source: string, selector: string): string[] {
  return allRules(source)
    .filter(([sel]) => sel.split(",").map((s) => s.trim()).includes(selector))
    .map(([, body]) => body);
}

function prop(block: string, name: string): string | undefined {
  return block.match(new RegExp(`(?:^|[;\\s])${name}\\s*:\\s*([^;]+)`))?.[1].trim();
}

/** The first block for `selector` that sets `name`. */
function valueOf(source: string, selector: string, name: string): string {
  for (const b of blocks(source, selector)) {
    const v = prop(b, name);
    if (v !== undefined) return v;
  }
  throw new Error(`${selector} does not set ${name}`);
}

const rem = (value: string) => parseFloat(value);

/* ---- colour helpers ------------------------------------------------------ */

function variables(source: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of source.matchAll(/--([a-z-]+):\s*(#[0-9a-fA-F]{6})/g)) out[m[1]] = m[2];
  return out;
}

function stampColour(name: string): string {
  const m = stampsCss.match(new RegExp(`\\.stamp--${name}\\s*\\{\\s*color:\\s*(#[0-9a-fA-F]{6})`));
  if (!m) throw new Error(`no colour for .stamp--${name}`);
  return m[1];
}

function rgb(hex: string): [number, number, number] {
  return [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)) as [number, number, number];
}

function luminance(hex: string): number {
  const lin = (c: number) => ((c /= 255) <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  const [r, g, b] = rgb(hex).map(lin);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

/** `fg` printed at `alpha` density over `bg`, as a hex colour. */
function blend(fg: string, bg: string, alpha: number): string {
  const mixed = rgb(fg).map((c, i) => Math.round(c * alpha + rgb(bg)[i] * (1 - alpha)));
  return "#" + mixed.map((c) => c.toString(16).padStart(2, "0")).join("");
}

const v = variables(paperCss);

/* ---- the stage ----------------------------------------------------------- */

describe("night-time stage", () => {
  it("is dark", () => {
    expect(luminance(v["stage-bg"])).toBeLessThan(0.03);
    expect(valueOf(paperCss, "body", "background-color")).toBe("var(--stage-bg)");
  });

  it("puts the rolls left of the printer from 900 px, and above it below that", () => {
    expect(paperCss).toMatch(
      /@media \(min-width: 900px\)\s*\{\s*\.stage\s*\{\s*grid-template-columns:\s*17rem minmax\(0, 1fr\)/,
    );
    expect(paperCss).toMatch(/grid-template-areas:\s*"head head"\s*"rolls main"\s*"foot foot"/);
    expect(valueOf(paperCss, ".session-list", "grid-area")).toBe("rolls");
    // below 900 px there is one column, so the rolls (first in the page) sit above the printer
    expect(blocks(paperCss, ".stage")[0]).toMatch(/grid-template-columns:\s*minmax\(0, 1fr\)/);
  });
});

/* ---- readable contrast --------------------------------------------------- */

describe("readable contrast (WCAG AA, 4.5:1 for text)", () => {
  const pairs: [string, string, string][] = [
    ["heading on the stage", v["stage-ink"], v["stage-bg"]],
    ["explanation on the stage", v["stage-muted"], v["stage-bg"]],
    ["footer link on the stage", v["link-on-dark"], v["stage-bg"]],
    ["ink on paper", v.ink, v["paper-bg"]],
    ["ink on a green bar", v.ink, v.band],
    ["lightest ink density on paper", blend(v.ink, v["paper-bg"], MIN_INK), v["paper-bg"]],
    ["lightest ink density on a green bar", blend(v.ink, v.band, MIN_INK), v.band],
    ["grey line numbers on paper", v.muted, v["paper-bg"]],
    ["grey line numbers on a green bar", v.muted, v.band],
    ["green text on paper", v.green, v["paper-bg"]],
    ["red text on paper", v.red, v["paper-bg"]],
    ["red marker text on a green bar", v.red, v.band],
    ["SUPPORTED stamp on a green bar", stampColour("supported"), v.band],
    ["CONTRADICTED stamp on a green bar", stampColour("contradicted"), v.band],
    ["UNVERIFIED stamp on a green bar", stampColour("unverified"), v.band],
    ["record switch key on the stage", v["stage-ink"], v["stage-bg"]],
    ["the chosen record switch key", v.ink, v.band],
    ["totals under the switch", v["stage-muted"], v["stage-bg"]],
    ["NO STATEMENT stamp on a green bar", stampColour("no-statement"), v.band],
    ["SUPPORTED stamp on paper", stampColour("supported"), v["paper-bg"]],
    ["CONTRADICTED stamp on paper", stampColour("contradicted"), v["paper-bg"]],
    ["UNVERIFIED stamp on paper", stampColour("unverified"), v["paper-bg"]],
    ["NO STATEMENT stamp on paper", stampColour("no-statement"), v["paper-bg"]],
    ["key label on a key", v["key-ink"], v["key-face"]],
    ["white label on the red key", "#ffffff", v["key-red"]],
    ["label on a key held down", v["key-on-ink"], v["key-on"]],
    ["printed text on the front panel", v["panel-ink"], v["panel-bg"]],
    ["display text", v["lcd-ink"], v["lcd-bg"]],
    ["display warning", v["lcd-warn"], v["lcd-bg"]],
    ["error text on the stage", v["lcd-warn"], v["stage-bg"]],
    ["the clerk's words in his bubble", v.ink, v["bubble-bg"]],
    ["roll label on a roll", v.ink, v["paper-bg"]],
    ["LIVE badge", "#ffffff", "#b3261e"],
  ];

  it.each(pairs)("%s", (_name, foreground, background) => {
    expect(foreground, "colour not found in the stylesheet").toMatch(/^#[0-9a-fA-F]{6}$/);
    expect(background, "colour not found in the stylesheet").toMatch(/^#[0-9a-fA-F]{6}$/);
    expect(contrast(foreground, background)).toBeGreaterThanOrEqual(4.5);
  });

  it.each([
    ["on the stage", v.focus, v["stage-bg"]],
    ["on the printer's panel", v.focus, v["panel-bg"]],
    ["on the paper", v["focus-paper"], v["paper-bg"]],
    ["on a green bar", v["focus-paper"], v.band],
  ])("the focus ring is clearly visible %s (3:1)", (_where, ring, ground) => {
    expect(contrast(ring, ground)).toBeGreaterThanOrEqual(3);
  });

  it("keeps the lightest ink density in step with the stylesheet's own floor", () => {
    expect(MIN_INK).toBe(0.82);
  });
});

describe("keyboard focus is visible", () => {
  it("outlines focused keys, links and rolls, in a different colour on the paper", () => {
    expect(valueOf(paperCss, "button:focus-visible", "outline")).toBe("3px solid var(--focus)");
    expect(blocks(paperCss, "a:focus-visible")).toHaveLength(1);
    expect(valueOf(paperCss, ".paper-roll button:focus-visible", "outline-color")).toBe("var(--focus-paper)");
  });
});

/* ---- the printer and its keys ------------------------------------------- */

describe("printer front panel", () => {
  it("has chunky keys that are tall enough to press with a thumb (44 px)", () => {
    expect(rem(valueOf(paperCss, ".key", "min-height"))).toBeGreaterThanOrEqual(2.75);
    expect(valueOf(paperCss, ".key", "border-bottom-width")).toBe("4px");
    expect(valueOf(paperCss, ".key", "box-shadow")).toMatch(/rgba\(0, 0, 0, 0\.6\)/);
  });

  it("a key goes down when pressed, and a held key stays down", () => {
    const pressed = blocks(paperCss, ".key:active:not(:disabled)")[0];
    expect(prop(pressed, "transform")).toBe("translateY(3px)");
    expect(prop(pressed, "border-bottom-width")).toBe("1px");
    expect(blocks(paperCss, '.key[aria-pressed="true"]').length).toBeGreaterThan(0);
  });

  it("has a red key, a status light in four states, and a slot for the paper", () => {
    expect(blocks(paperCss, ".key--red")[0]).toMatch(/var\(--key-red\)/);
    for (const light of ["ready", "busy", "error"]) {
      expect(blocks(paperCss, `.led--${light}`).length).toBeGreaterThanOrEqual(1);
      expect(valueOf(paperCss, `.led--${light}`, "background")).toMatch(/^#/);
    }
    expect(valueOf(paperCss, ".printer__slot", "background")).toBe("#05070a");
  });

  it("turns the state word to the warning colour when the paper is jammed", () => {
    expect(valueOf(paperCss, '.printer[data-light="error"] .lcd__state', "color")).toBe("var(--lcd-warn)");
  });

  it("pulses the amber light only when motion is welcome", () => {
    expect(paperCss).toMatch(/@media \(prefers-reduced-motion: no-preference\)\s*\{\s*\.led--busy\s*\{\s*animation:/);
  });

  it("sits above the paper, and the paper is tucked under its lip", () => {
    expect(Number(valueOf(paperCss, ".printer", "z-index"))).toBeGreaterThan(
      Number(valueOf(paperCss, ".paper-roll", "z-index")),
    );
    expect(valueOf(paperCss, ".paper-roll", "margin")).toMatch(/^-6px /);
  });
});

/* ---- the paper ----------------------------------------------------------- */

describe("paper", () => {
  it("feeds out downward and fills most of the screen", () => {
    expect(rem(valueOf(paperCss, ".paper-roll--whole .paper-piece__sheet", "min-height"))).toBeGreaterThanOrEqual(60);
    expect(valueOf(paperCss, ".paper-roll--whole .paper-piece__sheet", "min-height")).toMatch(/vh$/);
  });

  it("is narrower than the printer, with pale green bars and feed holes", () => {
    expect(valueOf(paperCss, ".paper-roll", "margin")).toMatch(/1\.6rem/);
    expect(paperCss).toMatch(/--band:\s*#d9f0d0/);
    expect(paperCss).toMatch(/repeating-linear-gradient/);
    expect(blocks(paperCss, ".tractor-holes--left")).toHaveLength(1);
    expect(blocks(paperCss, ".tractor-holes--right")).toHaveLength(1);
    expect(valueOf(paperCss, ".session-break", "border-top")).toMatch(/dashed/);
  });

  it("clips only sideways, so a swung torn piece cannot add a scroll bar", () => {
    expect(valueOf(paperCss, ".paper-roll", "overflow-x")).toBe("clip");
    expect(blocks(paperCss, ".paper-roll").some((b) => /overflow\s*:\s*hidden/.test(b))).toBe(false);
  });
});

describe("type", () => {
  it("prints in Doto, weight 900, falling back to Courier", () => {
    expect(paperCss).toMatch(/--font-print:\s*"Doto", "Courier New", Courier, monospace;/);
    expect(valueOf(paperCss, ".print-lines", "font-family")).toBe("var(--font-print)");
    expect(valueOf(paperCss, ".print-lines", "font-weight")).toBe("900");
  });

  it("gives each line its own ink density", () => {
    expect(valueOf(paperCss, ".print-line__text", "opacity")).toBe("var(--density, 1)");
  });
});

describe("printing animation", () => {
  it("sweeps a print head across the line that has just printed, about 0.4 s", () => {
    expect(paperCss).toMatch(/\.print-line--fresh \.print-line__text\s*\{\s*animation:\s*ink-reveal 0\.4s linear both/);
    expect(paperCss).toMatch(/\.print-line--fresh::before[\s\S]*?animation:\s*head-sweep 0\.4s linear forwards/);
    expect(paperCss).toMatch(/@keyframes ink-reveal\s*\{\s*from\s*\{\s*clip-path:\s*inset\(0 100% 0 0\)/);
    expect(paperCss).toMatch(/@keyframes head-sweep[\s\S]*?100%\s*\{[^}]*opacity:\s*0/); // the head fades out
  });

  it("only does so for visitors who have not asked for less motion", () => {
    expect(paperCss).toMatch(
      /@media \(prefers-reduced-motion: no-preference\)\s*\{\s*\.print-line--fresh \.print-line__text/,
    );
  });

  it("switches every animation off when asked for less motion", () => {
    expect(paperCss).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*?animation: none !important/);
  });
});

/* ---- stamps -------------------------------------------------------------- */

describe("rubber stamps", () => {
  it("are double-ruled, tilted, inky, and roughened by the shared filter", () => {
    const block = blocks(stampsCss, ".stamp")[0];
    expect(prop(block, "border")).toBe("5px double currentColor");
    expect(prop(block, "mix-blend-mode")).toBe("multiply");
    expect(prop(block, "filter")).toBe("url(#rough-ink)");
    expect(prop(block, "transform")).toBe("translateY(var(--ty)) rotate(var(--tilt))");
    expect(prop(block, "text-transform")).toBe("uppercase");
  });

  it("come in three sizes, and each is tilted more than the one before", () => {
    const size = (n: string) => rem(valueOf(stampsCss, `.stamp--${n}`, "font-size"));
    const tilt = (n: string) => Math.abs(parseFloat(valueOf(stampsCss, `.stamp--${n}`, "--tilt")));
    expect(size("small")).toBeLessThan(size("medium"));
    expect(size("medium")).toBeLessThan(size("huge"));
    expect(tilt("small")).toBeLessThan(tilt("medium"));
    expect(tilt("medium")).toBeLessThan(tilt("huge"));
  });

  it("make the overall stamp the biggest type on the paper", () => {
    const sizes = allRules(paperCss)
      .filter(([sel]) => /\.print-line/.test(sel)) // every size used for text on the paper
      .map(([, body]) => prop(body, "font-size"))
      .filter((s): s is string => !!s && s.endsWith("rem"))
      .map(rem);
    expect(sizes.length).toBeGreaterThan(0);
    expect(rem(valueOf(stampsCss, ".stamp--huge", "font-size"))).toBeGreaterThan(Math.max(...sizes) * 1.8);
  });

  it("are pressed over the right-hand end of their line", () => {
    const block = blocks(stampsCss, ".print-line .stamp")[0];
    expect(prop(block, "position")).toBe("absolute");
    expect(prop(block, "right")).toBeDefined();
    expect(prop(block, "top")).toBe("50%");
  });

  it("land with a thump after the line has printed, and only if motion is welcome", () => {
    expect(stampsCss).toMatch(
      /@media \(prefers-reduced-motion: no-preference\)\s*\{\s*\.print-line--fresh \.stamp\s*\{\s*animation:\s*stamp-thump 0\.35s ease-out 0\.4s backwards/,
    );
    const frames = stampsCss.match(/@keyframes stamp-thump\s*\{([\s\S]*?)\n\}/)![1];
    expect(frames).toMatch(/scale\(1\.9\)/); // lands from above
    expect(frames).toMatch(/scale\(0\.92\)/); // a squash
    expect(frames).toMatch(/100%[^}]*scale\(1\)/); // at rest
  });

  it("go under their text on a phone, clear of it, so the words stay readable", () => {
    const phone = stampsCss.slice(stampsCss.indexOf("@media (max-width: 640px)"));
    expect(phone).toMatch(/\.print-line \.stamp\s*\{\s*position:\s*static/);
    expect(phone).toMatch(/\.print-line \.stamp\s*\{\s*margin-top:\s*0\.35rem/);
  });
});

describe("red marker", () => {
  it("is a hand-drawn ellipse, not a CSS border", () => {
    expect(valueOf(stampsCss, ".undeclared-circle", "border")).toBe("none");
    const ring = blocks(stampsCss, ".undeclared-circle__ring path")[0];
    expect(prop(ring, "stroke")).toBe("#c0262d");
    expect(prop(ring, "filter")).toBe("url(#marker-ink)");
    expect(prop(ring, "vector-effect")).toBe("non-scaling-stroke");
  });

  it("leaves room round the text, because an ellipse cuts the corners of a rectangle", () => {
    // A real browser showed the first letters struck through when the ring hugged the text.
    const overhang = -parseFloat(valueOf(stampsCss, ".undeclared-circle__ring", "left"));
    const extra = parseFloat(valueOf(stampsCss, ".undeclared-circle__ring", "width").match(/\+ ([\d.]+)em/)![1]);
    expect(overhang).toBeGreaterThanOrEqual(1.5);
    expect(extra).toBeCloseTo(overhang * 2, 5); // the same overhang on both sides
    expect(parseFloat(valueOf(stampsCss, ".undeclared-circle", "padding").split(" ")[1])).toBeGreaterThanOrEqual(2);
  });

  it("has phone rules that come after the base rules, so they win the cascade", () => {
    // The first version put the phone override above the base rule, which then beat it.
    const at = (needle: string) => stampsCss.indexOf(needle);
    const phoneRing = stampsCss.lastIndexOf(".undeclared-circle__ring {");
    expect(phoneRing).toBeGreaterThan(at(".undeclared-circle__ring path"));
    expect(stampsCss.lastIndexOf("@media (max-width: 640px)")).toBeGreaterThan(at(".undeclared-circle__ring path"));
    const phone = stampsCss.slice(stampsCss.lastIndexOf("@media (max-width: 640px)"));
    expect(phone).toMatch(/\.undeclared-circle__ring\s*\{\s*top:\s*-0\.8em;\s*left:\s*-1\.3em/);
    // and it still leaves the same room on both sides
    expect(phone).toMatch(/width:\s*calc\(100% \+ 2\.6em\)/);
  });

  it("the arrow in the margin is drawn in the same red marker", () => {
    expect(valueOf(paperCss, ".marker-arrow svg", "stroke")).toBe("#c0262d");
    expect(valueOf(paperCss, ".marker-arrow svg", "filter")).toBe("url(#marker-ink)");
    expect(valueOf(paperCss, ".marker-arrow", "pointer-events")).toBe("none");
  });
});

/* ---- the tear ------------------------------------------------------------ */

describe("a torn page", () => {
  const points = (selector: string) => {
    const clip = valueOf(paperCss, selector, "clip-path");
    return clip.slice(clip.indexOf("(") + 1, clip.lastIndexOf(")")).split(",").length;
  };

  it("has a jagged edge on each piece", () => {
    expect(points(".paper-roll--torn .paper-piece--upper .paper-piece__sheet")).toBeGreaterThanOrEqual(20);
    expect(points(".paper-piece--lower .paper-piece__sheet")).toBeGreaterThanOrEqual(20);
  });

  it("shifts and turns the lower piece by one to two degrees", () => {
    const turn = parseFloat(valueOf(paperCss, ".paper-piece--lower", "transform").match(/rotate\(([\d.]+)deg\)/)![1]);
    expect(turn).toBeGreaterThanOrEqual(1);
    expect(turn).toBeLessThanOrEqual(2);
    expect(valueOf(paperCss, ".paper-piece--lower", "transform")).toMatch(/translate\(/);
  });

  it("casts shadows, from the outer element so the clip cannot cut them off", () => {
    expect(valueOf(paperCss, ".paper-piece", "filter")).toMatch(/^drop-shadow\(/);
    expect(valueOf(paperCss, ".paper-piece--lower", "filter")).toMatch(/^drop-shadow\(/);
    expect(blocks(paperCss, ".paper-piece").some((b) => /clip-path/.test(b))).toBe(false);
  });

  it("is still a long page once torn, not a short scrap", () => {
    const lower = parseFloat(valueOf(paperCss, ".paper-piece--lower .paper-piece__sheet", "min-height"));
    expect(lower).toBeGreaterThanOrEqual(50);
    expect(valueOf(paperCss, ".paper-piece--lower .paper-piece__sheet", "min-height")).toMatch(/vh$/);
  });

  it("leaves a gap that the stage shows through", () => {
    expect(rem(valueOf(paperCss, ".paper-gap", "height"))).toBeGreaterThan(0);
    expect(blocks(paperCss, ".paper-roll").some((b) => /background/.test(b))).toBe(false);
  });
});

/* ---- the clerk ----------------------------------------------------------- */

describe("ghost clerk", () => {
  it("is twice his old size (60 px), 96 px on a phone", () => {
    expect(valueOf(paperCss, ".ghost-clerk__svg", "width")).toBe("120px");
    expect(valueOf(paperCss, ".ghost-clerk__svg", "height")).toBe("120px");
    const phone = paperCss.slice(paperCss.indexOf("@media (max-width: 640px)"));
    expect(phone).toMatch(/\.ghost-clerk__svg\s*\{\s*width:\s*96px;\s*height:\s*96px/);
  });

  it("sits on the printer rather than floating over the page", () => {
    expect(valueOf(paperCss, ".ghost-clerk", "position")).toBe("relative");
    expect(valueOf(paperCss, ".ghost-clerk", "margin")).toMatch(/-0\.8rem 0$/); // overlaps the printer's top edge
    expect(Number(valueOf(paperCss, ".ghost-clerk", "z-index"))).toBeGreaterThan(
      Number(valueOf(paperCss, ".printer", "z-index")),
    );
  });

  it("bobs when idle and jumps once when alarmed, only if motion is welcome", () => {
    expect(paperCss).toMatch(/@media \(prefers-reduced-motion: no-preference\)\s*\{\s*\.ghost-clerk__bob\s*\{\s*animation:\s*ghost-bob 3\.2s ease-in-out infinite/);
    expect(paperCss).toMatch(/\.ghost-clerk__svg\[data-expression="alarmed"\]\s*\{\s*animation:\s*ghost-jump[^;]* 1;/);
    expect(paperCss).toMatch(/@keyframes ghost-jump[\s\S]*?translateY\(-30px\)/);
  });
});

/* ---- phones -------------------------------------------------------------- */

describe("phones", () => {
  const phone = paperCss.slice(paperCss.indexOf("@media (max-width: 640px)"));

  it("hides the feed holes and tightens the paper", () => {
    expect(phone).toMatch(/\.tractor-holes\s*\{\s*display:\s*none/);
    expect(phone).toMatch(/\.paper-roll\s*\{[^}]*--gutter:\s*0\.4rem/);
  });

  it("stacks the rolls in one column", () => {
    expect(blocks(paperCss, ".session-list ul")[0]).toMatch(/repeat\(auto-fill, minmax\(15rem, 1fr\)\)/);
    expect(paperCss).toMatch(/@media \(min-width: 900px\)\s*\{\s*\.session-list ul\s*\{\s*grid-template-columns:\s*minmax\(0, 1fr\)/);
  });

  it("lets long text wrap instead of scrolling sideways", () => {
    expect(valueOf(paperCss, ".print-line__text", "overflow-wrap")).toBe("anywhere");
    expect(valueOf(paperCss, ".spool__title", "overflow-wrap")).toBe("anywhere");
    expect(valueOf(paperCss, ".stage__main", "min-width")).toBe("0");
  });

  it("puts the stamp under the text, not over it", () => {
    expect(phone).toMatch(/\.print-line--stamped \.print-line__text,\s*\.print-line--overall \.print-line__text\s*\{\s*padding-right:\s*0/);
  });

  it("wraps the keys instead of overflowing", () => {
    expect(valueOf(paperCss, ".printer__keys", "flex-wrap")).toBe("wrap");
    expect(valueOf(paperCss, ".key-group", "flex-wrap")).toBe("wrap");
  });
});

/* ---- tear off report (print) -------------------------------------------- */

describe("tear off report (print)", () => {
  it("shows only the report: everything else is hidden", () => {
    expect(printCss).toMatch(/\.print-report\s*\{\s*display:\s*none;\s*\}/); // hidden on screen
    expect(printCss).toMatch(/@media print[\s\S]*?\.screen-only\s*\{\s*display:\s*none !important/);
    expect(printCss).toMatch(/@media print[\s\S]*?\.print-report\s*\{\s*display:\s*block/);
  });

  it("is plain monospace on white with no backgrounds", () => {
    expect(printCss).toMatch(/@media print[\s\S]*?background:\s*none !important/);
    expect(printCss).toMatch(/font-family:\s*"Courier New", Courier, monospace/);
  });
});
