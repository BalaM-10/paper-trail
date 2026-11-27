import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { splitRolls } from "../lib/rolls";
import { BANNED, demoEntries, demoText, ok, visibleLanguage } from "./demo";

/*
  One roll per turn (paper-trail-turns R2.6, R2.10, R3). The demo's session D
  has two turns; between them a person deleted two files.
*/

const rollsOfD = splitRolls(demoEntries).filter((r) => r.sessionId === "demo-session-d");
const [turn1, turn2] = rollsOfD;

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input).includes("/api/")) throw new TypeError("no server");
    return ok(demoText);
  });
});
afterEach(() => vi.restoreAllMocks());

async function openDemo() {
  render(<App />);
  await screen.findByRole("button", { name: /Cleared the build cache/ });
  await within(screen.getByRole("status", { name: "Paper status" })).findByText("Paper intact");
  return screen.getByRole("region", { name: "Printout" });
}
const feed = () => screen.getByRole("button", { name: "Feed one line" });
function step(count: number) {
  for (let i = 0; i < count; i++) fireEvent.click(feed());
}
const rollButton = (title: RegExp) => screen.getByRole("button", { name: title });

describe("one roll per turn, in the list of rolls", () => {
  it("lists each turn as its own roll, titled by its statement and numbered in its session", async () => {
    await openDemo();
    const nav = screen.getByRole("navigation", { name: "Sessions" });
    const first = within(nav).getByRole("button", { name: /Wrote the plan\./ });
    const second = within(nav).getByRole("button", { name: /Cleared two drafts\./ });
    expect(first).toHaveTextContent("turn 1 of 2");
    expect(second).toHaveTextContent("turn 2 of 2");
    expect(first.querySelector(".stamp")).toHaveTextContent("SUPPORTED");
    expect(second.querySelector(".stamp")).toHaveTextContent("SUPPORTED");
    expect(within(nav).getAllByRole("listitem")).toHaveLength(6);
  });

  it("says nothing about turns for a session that has only one", async () => {
    await openDemo();
    for (const name of [/Read main\.py/, /Cleared the build cache/, /No statement written/]) {
      expect(rollButton(name).textContent).not.toMatch(/turn \d of/);
    }
  });

  it("opens, as before, on the contradicted roll, and only that roll is picked", async () => {
    await openDemo();
    expect(rollButton(/Cleared the build cache/)).toHaveAttribute("aria-pressed", "true");
    expect(rollButton(/Wrote the plan\./)).toHaveAttribute("aria-pressed", "false");
    expect(rollButton(/Cleared two drafts\./)).toHaveAttribute("aria-pressed", "false");
  });

  it("uses plain words and no word the page may not show", async () => {
    await openDemo();
    fireEvent.click(rollButton(/Cleared two drafts\./));
    expect(visibleLanguage()).not.toMatch(BANNED);
  });
});

describe("choosing a turn prints only that turn", () => {
  it("prints the second turn's lines, with their real line numbers, and none of the first's", async () => {
    const paper = await openDemo();
    fireEvent.click(rollButton(/Cleared two drafts\./));
    expect(rollButton(/Cleared two drafts\./)).toHaveAttribute("aria-pressed", "true");
    expect(paper.querySelectorAll(".print-line--pending")).toHaveLength(turn2.entries.length);

    step(turn2.entries.length);

    const numbers = Array.from(paper.querySelectorAll<HTMLElement>(".print-line__no"), (el) => el.textContent);
    expect(numbers).toEqual(turn2.entries.map((e) => String(e.seq)));
    expect(within(paper).queryByText(/Agent wrote drafts\/plan\.md\./)).toBeNull(); // turn 1's tool call
    expect(within(paper).getByText(/Agent ran the command: Remove-Item drafts\/draft-1\.txt/)).toBeInTheDocument();
  });

  it("cites the real line numbers in a verdict's evidence", async () => {
    const paper = await openDemo();
    fireEvent.click(rollButton(/Cleared two drafts\./));
    step(turn2.entries.length);
    const stop = turn2.entries.find((e) => e.kind === "witness" && e.data.event === "stop")!;
    expect(
      within(paper).getByText(`Agent said it deleted drafts/draft-1.txt. Witness agrees (line ${stop.seq}).`),
    ).toBeInTheDocument();
    expect(document.getElementById(`line-${stop.seq}`)).not.toBeNull(); // and that line is on this paper
  });

  it("starts the replay again from the top when another turn is chosen", async () => {
    const paper = await openDemo();
    fireEvent.click(rollButton(/Wrote the plan\./));
    step(3);
    expect(paper.querySelectorAll(".print-line:not(.print-line--pending)")).toHaveLength(3);
    fireEvent.click(rollButton(/Cleared two drafts\./));
    expect(paper.querySelectorAll(".print-line:not(.print-line--pending)")).toHaveLength(0);
    expect(document.querySelector(".lcd__state")).toHaveTextContent("Ready");
  });

  it("stamps the turn's own overall verdict, and the clerk is pleased", async () => {
    const paper = await openDemo();
    fireEvent.click(rollButton(/Cleared two drafts\./));
    step(turn2.entries.length);
    expect(within(paper).getByText("SUPPORTED", { selector: ".stamp--huge" })).toBeInTheDocument();
    expect(screen.getByText(/Everything checks out/)).toBeInTheDocument();
  });
});

describe("what a person changed between two turns", () => {
  async function printSecondTurn() {
    const paper = await openDemo();
    fireEvent.click(rollButton(/Cleared two drafts\./));
    step(turn2.entries.length);
    return paper;
  }

  it("is one plain line: no stamp, no red ring, no arrow, nothing to click through", async () => {
    const paper = await printSecondTurn();
    const sentence = "Between turns, outside the agent: deleted drafts/old-a.txt, drafts/old-b.txt.";
    const text = within(paper).getByText(sentence);
    const line = text.closest("li") as HTMLElement;
    expect(line).toHaveClass("print-line--between");
    expect(line.querySelector(".stamp")).toBeNull();
    expect(line.querySelector(".undeclared-circle")).toBeNull();
    expect(line.querySelector(".marker-arrow")).toBeNull();
    expect(line).not.toHaveClass("print-line--stamped", "print-line--note");
    expect(text.closest("button")).toBeNull();
    // and nothing else on the paper is circled: the agent left nothing out
    expect(paper.querySelectorAll(".undeclared-circle")).toHaveLength(0);
    expect(paper.querySelectorAll(".marker-arrow")).toHaveLength(0);
  });

  it("is the second line of the turn that follows it, after the snapshot at the turn's start", async () => {
    const paper = await printSecondTurn();
    const lines = Array.from(paper.querySelectorAll(".print-line__text"), (el) => el.textContent);
    expect(lines[0]).toBe("Witness took a snapshot of the project at the start of this turn.");
    expect(lines[1]).toMatch(/^Between turns, outside the agent: deleted /);
  });

  it("is not on the first turn's paper", async () => {
    const paper = await openDemo();
    fireEvent.click(rollButton(/Wrote the plan\./));
    step(turn1.entries.length);
    expect(within(paper).queryByText(/Between turns/)).toBeNull();
  });

  it("compares the stop with the start of the turn, in words", async () => {
    const paper = await printSecondTurn();
    expect(
      within(paper).getByText(
        "Witness compared the project to the snapshot from the start of this turn. Deleted: drafts/draft-1.txt, drafts/draft-2.txt.",
      ),
    ).toBeInTheDocument();
  });
});

describe("the tear-off report names the turn", () => {
  it("has the turn, the between-turns line before the verdicts, and the fingerprint last", async () => {
    vi.spyOn(window, "print").mockImplementation(() => {});
    await openDemo();
    fireEvent.click(rollButton(/Cleared two drafts\./));
    fireEvent.click(screen.getByRole("button", { name: "Tear off report" }));
    const report = document.querySelector(".print-report") as HTMLElement;
    const paragraphs = Array.from(report.querySelectorAll("p"), (p) => p.textContent);
    expect(paragraphs).toContain("Session: demo-session-d");
    expect(paragraphs).toContain("Turn: 2 of 2");
    expect(paragraphs).toContain("Statement: Cleared two drafts.");
    const between = paragraphs.findIndex((p) => p?.startsWith("Between turns, outside the agent"));
    const firstVerdict = paragraphs.findIndex((p) => p?.startsWith("SUPPORTED: "));
    expect(between).toBeGreaterThan(-1);
    expect(between).toBeLessThan(firstVerdict);
    expect(paragraphs[paragraphs.length - 1]).toMatch(/^Fingerprint of the record: [0-9a-f]{64}/);
    expect(report).not.toHaveTextContent("Not mentioned in the statement");
  });

  it("leaves the turn out for a session that has one", async () => {
    vi.spyOn(window, "print").mockImplementation(() => {});
    await openDemo();
    fireEvent.click(screen.getByRole("button", { name: "Tear off report" }));
    const report = document.querySelector(".print-report") as HTMLElement;
    expect(report.textContent).not.toMatch(/Turn:/);
  });
});

describe("tampering still works on a turn", () => {
  it("tears the paper at a line of the chosen turn", async () => {
    await openDemo();
    fireEvent.click(rollButton(/Cleared two drafts\./));
    step(turn2.entries.length);
    const target = turn2.entries.find((e) => e.kind === "tool")!;
    fireEvent.click(screen.getByRole("button", { name: `Line ${target.seq}: pick to tamper with` }));
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    await within(screen.getByRole("status", { name: "Paper status" })).findByText(`Paper torn at line ${target.seq}`);
    expect(document.querySelector(".paper-roll--torn")).not.toBeNull();
  });
});
