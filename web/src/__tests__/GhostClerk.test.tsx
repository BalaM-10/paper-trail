import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { GhostClerk, ghostFor, type Expression, type GhostInput } from "../components/GhostClerk";
import { BANNED } from "./demo";

const base: GhostInput = {
  source: "demo",
  hasRecords: true,
  hasSession: true,
  preloaded: false,
  replayState: "idle",
  chainOk: true,
  brokenAt: null,
  tampered: false,
  tamperTarget: null,
  overallVerdict: null,
};

const say = (over: Partial<GhostInput>) => ghostFor({ ...base, ...over });

/** One input per state the clerk can be in. */
const STATES: [string, Partial<GhostInput>, Expression, RegExp][] = [
  ["loading", { source: "loading", hasRecords: false, hasSession: false }, "calm", /Warming up/],
  ["error", { source: "error", hasRecords: false, hasSession: false }, "alarmed", /jammed/],
  ["no records yet", { source: "api", hasRecords: false, hasSession: false }, "calm", /Nothing is recorded/],
  ["no session picked", { source: "api", hasSession: false }, "calm", /Pick a session/],
  ["demo opened a session itself", { preloaded: true }, "calm", /pre-loaded the interesting session\. Press PLAY/],
  ["session picked, idle", {}, "calm", /Press PLAY to start/],
  ["playing", { replayState: "playing" }, "calm", /press PAUSE/],
  ["paused", { replayState: "paused" }, "calm", /Press PLAY to continue/],
  ["done, SUPPORTED", { replayState: "done", overallVerdict: "SUPPORTED" }, "pleased", /Everything checks out/],
  ["done, CONTRADICTED", { replayState: "done", overallVerdict: "CONTRADICTED" }, "alarmed", /doesn't match what the witness saw/],
  ["done, UNVERIFIED", { replayState: "done", overallVerdict: "UNVERIFIED" }, "calm", /couldn't be confirmed/],
  ["done, NO_STATEMENT", { replayState: "done", overallVerdict: "NO_STATEMENT" }, "alarmed", /said nothing\. Click a red circle/],
  ["the build record is not published", { source: "build-missing", hasRecords: false, hasSession: false }, "calm", /build record isn't published yet\. Click Demo/],
  ["done, no verdict yet", { source: "api", replayState: "done" }, "calm", /Check this statement/],
  ["line picked", { tamperTarget: 10 }, "calm", /Line 10 picked\. Click TAMPER/],
  ["torn after tampering", { chainOk: false, brokenAt: 10, tampered: true }, "alarmed", /Someone's been at the paper\. Click RESTORE/],
  ["torn on disk", { chainOk: false, brokenAt: 7, tampered: false }, "alarmed", /Torn at line 7/],
];

const WARY_INPUT: Partial<GhostInput> = { replayState: "done", overallVerdict: "SUPPORTED", setupChanged: true };
const WARY_MESSAGE = "The statement checks out, but the recording setup changed in this turn. Read it with care.";

describe("when the recording setup changed", () => {
  it("does not say everything checks out: after the replay it is wary and says why", () => {
    const said = say(WARY_INPUT);
    expect(said.expression).toBe("wary");
    expect(said.message).toBe(WARY_MESSAGE);
    expect(said.message).not.toMatch(/Everything checks out|Remarkable/);
  });

  it("is short, plain, and uses no forbidden word", () => {
    expect(WARY_MESSAGE.length).toBeLessThanOrEqual(96);
    expect(WARY_MESSAGE).not.toMatch(BANNED);
  });

  it("keeps the usual calm messages until the replay has ended", () => {
    for (const replayState of ["idle", "playing", "paused"] as const) {
      const said = say({ replayState, overallVerdict: "SUPPORTED", setupChanged: true });
      expect(said.expression).toBe("calm");
      expect(said.message).not.toMatch(/recording setup/);
    }
  });

  it("does not soften a verdict that is already bad", () => {
    for (const [verdict, expression] of [["CONTRADICTED", "alarmed"], ["NO_STATEMENT", "alarmed"], ["UNVERIFIED", "calm"]] as const) {
      const said = say({ replayState: "done", overallVerdict: verdict, setupChanged: true });
      expect(said.expression).toBe(expression);
      expect(said.message).toBe(say({ replayState: "done", overallVerdict: verdict }).message);
    }
  });

  it("changes nothing when the setup did not change", () => {
    expect(say({ replayState: "done", overallVerdict: "SUPPORTED", setupChanged: false })).toEqual(
      say({ replayState: "done", overallVerdict: "SUPPORTED" }),
    );
    expect(say({ replayState: "done", overallVerdict: "SUPPORTED" }).expression).toBe("pleased");
  });

  it("a torn paper still outranks it", () => {
    expect(say({ ...WARY_INPUT, chainOk: false, brokenAt: 4 }).expression).toBe("alarmed");
  });

  it("draws the wary face: not the smile, with brows, eyes and a crooked mouth", () => {
    const wary = render(<GhostClerk {...base} {...WARY_INPUT} />).container.querySelector("svg")!;
    expect(wary).toHaveAttribute("data-expression", "wary");
    expect(wary.querySelectorAll('[data-part="eye"]')).toHaveLength(2);
    expect(wary.querySelectorAll('[data-part="brow"]')).toHaveLength(2);
    expect(wary.querySelectorAll('[data-part="mouth"]')).toHaveLength(1);
    const mouth = wary.querySelector('[data-part="mouth"]')!.getAttribute("d");
    const smile = render(<GhostClerk {...base} replayState="done" overallVerdict="SUPPORTED" />).container
      .querySelector('[data-part="mouth"]')!
      .getAttribute("d");
    expect(mouth).not.toBe(smile);
  });
});

describe("what the clerk says and how he looks", () => {
  it.each(STATES)("%s", (_name, input, expression, message) => {
    const said = say(input);
    expect(said.expression).toBe(expression);
    expect(said.message).toMatch(message);
  });

  it("a torn paper outranks everything else", () => {
    const said = say({ chainOk: false, brokenAt: 3, tampered: true, replayState: "playing", tamperTarget: 3 });
    expect(said.message).toMatch(/Click RESTORE/);
  });

  it("uses all four expressions", () => {
    const used = new Set([...STATES.map(([, input]) => say(input).expression), say(WARY_INPUT).expression]);
    expect(used).toEqual(new Set(["calm", "pleased", "alarmed", "wary"]));
  });
});

describe("every message", () => {
  const messages = STATES.map(([name, input]) => [name, say(input).message] as const);

  it.each(messages)("%s: short, plain, and says what to do next", (_n, message) => {
    expect(message.length).toBeLessThanOrEqual(96);
    expect(message).not.toMatch(BANNED);
    expect(message).toMatch(/\b(press|click|pick|ask|reload|check)\b/i);
  });

  it("uses the names printed on the printer's keys, in capitals", () => {
    const all = messages.map(([, m]) => m).join("\n");
    for (const key of ["PLAY", "PAUSE", "FEED", "TAMPER", "RESTORE"]) expect(all).toContain(key);
  });

  it("never mentions the old button names", () => {
    const all = messages.map(([, m]) => m).join("\n");
    expect(all).not.toMatch(/\bStep\b|Tamper with the paper|\bRestore\b/);
  });
});

describe("the drawing", () => {
  const inputFor = (expression: Expression): Partial<GhostInput> =>
    expression === "pleased"
      ? { replayState: "done", overallVerdict: "SUPPORTED" }
      : expression === "alarmed"
        ? { chainOk: false, brokenAt: 2, tampered: true }
        : expression === "wary"
          ? WARY_INPUT
          : {};

  it.each(["calm", "pleased", "alarmed", "wary"] as const)("draws the %s ghost with his eyeshade", (expression) => {
    const { container } = render(<GhostClerk {...base} {...inputFor(expression)} />);
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveAttribute("data-expression", expression);
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg.querySelector('[data-part="visor"]')).toHaveAttribute("fill", "#3a7d44");
    expect(svg.querySelectorAll('[data-part="eye"]')).toHaveLength(2);
    expect(svg.querySelector('[data-part="shadow"]')).not.toBeNull(); // he sits on something
  });

  it("gives each expression a different mouth", () => {
    const mouths = (["calm", "pleased", "alarmed", "wary"] as const).map((expression) => {
      const { container, unmount } = render(<GhostClerk {...base} {...inputFor(expression)} />);
      const mouth = container.querySelector('[data-part="mouth"]')!.outerHTML;
      unmount();
      return mouth;
    });
    expect(new Set(mouths).size).toBe(4);
  });

  it("puts his bubble first and his figure, with the bobbing wrapper, second", () => {
    const { container } = render(<GhostClerk {...base} />);
    const aside = container.querySelector("aside")!;
    expect(aside.children[0]).toHaveClass("ghost-clerk__message");
    expect(aside.children[1]).toHaveClass("ghost-clerk__figure");
    expect(aside.querySelector(".ghost-clerk__figure > .ghost-clerk__bob > svg")).not.toBeNull();
  });

  it("announces his message politely", () => {
    render(<GhostClerk {...base} />);
    const clerk = screen.getByRole("complementary", { name: "Ghost clerk" });
    const message = within(clerk).getByText(/Press PLAY to start/);
    expect(message).toHaveAttribute("aria-live", "polite");
  });
});
