import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Entry } from "../lib/chainCheck";
import { makeRecord, staticSite } from "./buildRecord";
import { BANNED, SESSION_B, commandSeq, demoEntries, demoText, ok, visibleLanguage } from "./demo";

afterEach(() => vi.restoreAllMocks());

const SETUP_LINE =
  "RECORDING SETUP CHANGED DURING THIS TURN: .kiro/hooks/record.py. Read this turn's record with care.";

function serveDemo() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input).includes("/api/")) throw new TypeError("no server");
    return ok(demoText);
  });
}

function serveLive(entries: Entry[] = demoEntries) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input) === "/api/ledger") return ok(JSON.stringify(entries));
    throw new TypeError("unexpected " + String(input));
  });
}

async function openDemo() {
  render(<App />);
  await screen.findByRole("button", { name: /Cleared the build cache/ });
  await within(screen.getByRole("status", { name: "Paper status" })).findByText("Paper intact");
}

const key = () => screen.getByRole("button", { name: "Exceptions only" });
const skip = () => fireEvent.click(screen.getByRole("button", { name: "Skip to end" }));
const paper = () => screen.getByRole("region", { name: "Printout" });
const roll = (name: RegExp) => screen.getByRole("button", { name });
const printed = () => Array.from(paper().querySelectorAll(".print-line:not(.print-line--pending):not(.print-line--filter-note) .print-line__text"), (e) => e.textContent ?? "");
const notes = () => Array.from(paper().querySelectorAll(".print-line--filter-note .print-line__text"), (e) => e.textContent);

describe("the EXCEPTIONS ONLY key", () => {
  it("is on the printer, off at first, and a real button that says whether it is down", async () => {
    serveDemo();
    await openDemo();
    const k = key();
    expect(k.tagName).toBe("BUTTON");
    expect(k).toHaveAttribute("type", "button");
    expect(k).toHaveAttribute("aria-pressed", "false");
    expect(k.closest(".printer")).not.toBeNull();
    expect(k).toHaveTextContent("Exceptions only");
  });

  it("is operated with the keyboard: it takes focus and a press toggles it", async () => {
    serveDemo();
    await openDemo();
    key().focus();
    expect(key()).toHaveFocus();
    fireEvent.click(key()); // Enter and Space on a button arrive as a click
    expect(key()).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(key());
    expect(key()).toHaveAttribute("aria-pressed", "false");
  });

  it("uses no word the page is forbidden to use", async () => {
    serveDemo();
    await openDemo();
    fireEvent.click(key());
    skip();
    expect(visibleLanguage(paper())).not.toMatch(BANNED);
    expect(visibleLanguage(key())).not.toMatch(BANNED);
  });
});

describe("in the Demo", () => {
  it("shows only what needs a look on the cleanup roll, and says how many lines are hidden", async () => {
    serveDemo();
    await openDemo();
    fireEvent.click(key());
    skip();
    expect(printed()).toEqual([
      "Witness saw sample/notes.txt deleted. The agent never mentioned it.",
      "Overall: the statement does not match the evidence.",
    ]);
    // the cleanup roll has 6 lines in the record; one more is made up for display, and 2 stay on the paper
    expect(notes()).toEqual(["5 lines hidden."]);
    expect(screen.queryByText("Nothing to flag in this turn.")).toBeNull();
    expect(paper().querySelectorAll(".print-line--pending")).toHaveLength(0);
  });

  it("says there is nothing to flag on a roll that is all SUPPORTED", async () => {
    serveDemo();
    await openDemo();
    fireEvent.click(key());
    fireEvent.click(roll(/Read main\.py and wrote a notes file/));
    expect(notes()).toEqual(["8 lines hidden.", "Nothing to flag in this turn."]);
    expect(printed()).toEqual([]);
  });

  it("keeps the between-turns line and NO STATEMENT, and drops the rest", async () => {
    serveDemo();
    await openDemo();
    fireEvent.click(key());
    fireEvent.click(roll(/Cleared two drafts/));
    skip();
    expect(printed()).toEqual(["Between turns, outside the agent: deleted drafts/old-a.txt, drafts/old-b.txt."]);
    fireEvent.click(roll(/No statement written/));
    skip();
    const lines = printed();
    expect(lines.at(-1)).toBe("Overall: the agent changed files and said nothing.");
    expect(lines.filter((l) => l.startsWith("Witness saw"))).toHaveLength(2);
  });

  it("keeps the loud setup line and nothing else on the roll that has one", async () => {
    serveDemo();
    await openDemo();
    fireEvent.click(key());
    fireEvent.click(roll(/Edited the record hook/));
    skip();
    expect(printed()).toEqual([SETUP_LINE]);
    expect(notes()).toEqual(["9 lines hidden."]);
  });

  it("starts the replay again from the top when the key changes, and the paper has no leftovers", async () => {
    serveDemo();
    await openDemo();
    skip();
    expect(paper().querySelectorAll(".print-line--pending")).toHaveLength(0);
    fireEvent.click(key());
    expect(printed()).toEqual([]); // blank paper, ready to print the lines that are left
    expect(paper().querySelectorAll(".print-line--pending")).toHaveLength(2);
    fireEvent.click(key());
    expect(paper().querySelectorAll(".print-line--pending")).toHaveLength(7);
    expect(notes()).toEqual([]);
  });

  it("keeps the line where the paper is torn, even though it is a plain tool line", async () => {
    serveDemo();
    await openDemo();
    fireEvent.click(key());
    const target = commandSeq(SESSION_B);
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    await waitFor(() => expect(screen.getByRole("status", { name: "Paper status" })).toHaveTextContent(`Paper torn at line ${target}`));
    skip();
    expect(document.getElementById(`line-${target}`)).not.toBeNull();
    expect(paper().querySelector(".paper-gap")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Exceptions only" })).toHaveAttribute("aria-pressed", "true");
  });

  it("leaves the printed report whole: the key only changes what the paper shows", async () => {
    serveDemo();
    await openDemo();
    fireEvent.click(key());
    const report = document.querySelector(".print-report")!;
    expect(report.textContent).toContain("Witness saw sample/notes.txt deleted");
    expect(report.textContent).toContain("SUPPORTED: Agent said it deleted sample/cache/output.bin");
  });
});

describe("in How this was built", () => {
  it("works on the build record too", async () => {
    const build = await makeRecord([
      { id: "build-1", tools: 3, outcome: "supported", summary: "Wrote the recorder." },
      { id: "build-2", tools: 2, outcome: "contradicted", summary: "Tidied the folder." },
    ]);
    const site = staticSite(demoText, build.text, null);
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => site(input));
    await openDemo();
    fireEvent.click(screen.getByRole("button", { name: "How this was built" }));
    await screen.findByRole("button", { name: /Wrote the recorder/ });
    fireEvent.click(key());
    expect(key()).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(roll(/Wrote the recorder/));
    expect(notes()).toEqual([expect.stringMatching(/^\d+ lines hidden\.$/), "Nothing to flag in this turn."]);
    fireEvent.click(roll(/Tidied the folder/));
    skip();
    expect(screen.queryByText("Nothing to flag in this turn.")).toBeNull();
    expect(printed().some((l) => l.startsWith("Overall: the statement does not match"))).toBe(true);
  });
});

describe("on the live record", () => {
  it("works when the page is served by the local server", async () => {
    serveLive();
    render(<App />);
    await screen.findByText("LIVE");
    await screen.findByRole("button", { name: /Cleared the build cache/ });
    await within(screen.getByRole("status", { name: "Paper status" })).findByText("Paper intact");
    expect(key()).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(key());
    expect(key()).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(roll(/Cleared the build cache/));
    skip();
    expect(printed()).toHaveLength(2);
    expect(notes()).toEqual(["5 lines hidden."]);
  });
});

describe("the loud setup line, with or without the key", () => {
  it("is printed on the page as a line of its own, in the setup style", async () => {
    serveDemo();
    await openDemo();
    fireEvent.click(roll(/Edited the record hook/));
    skip();
    const loud = paper().querySelector(".print-line--setup")!;
    expect(loud).not.toBeNull();
    expect(loud.querySelector(".print-line__text")!.textContent).toBe(SETUP_LINE);
    expect(paper().querySelectorAll(".print-line--setup")).toHaveLength(1);
  });

  it("is in the report that is printed, and only for the turn it happened in", async () => {
    serveDemo();
    await openDemo();
    fireEvent.click(roll(/Edited the record hook/));
    expect(document.querySelector(".print-report .print-setup")!.textContent).toBe(SETUP_LINE);
    fireEvent.click(roll(/Cleared the build cache/));
    expect(document.querySelector(".print-report .print-setup")).toBeNull();
  });
});

describe("the opening sentence", () => {
  it("opens the page", async () => {
    serveDemo();
    await openDemo();
    const header = document.querySelector(".page-header")!;
    const sentence =
      "Git records what changed. Paper Trail records what the agent claimed, what actually happened, and whether the two agree.";
    expect(header.textContent!.replace(/\s+/g, " ")).toContain(sentence);
    // it comes before the question
    const question = screen.getByRole("heading", { level: 1 });
    const tagline = header.querySelector(".page-header__tagline")!;
    expect(tagline.compareDocumentPosition(question) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
