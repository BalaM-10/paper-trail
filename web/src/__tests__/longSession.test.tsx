import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { entryText } from "../lib/entryText";
import type { Entry } from "../lib/chainCheck";
import { makeRecord, staticSite } from "./buildRecord";
import { demoText } from "./demo";

// Count how often a line is drawn: one call per line that is printed (blank lines do not call it).
vi.mock("../lib/entryText", async (importOriginal) => {
  const real = await importOriginal<typeof import("../lib/entryText")>();
  return { ...real, entryText: vi.fn(real.entryText) };
});

/** 1994 tool lines + 5 records + 1 line for what the agent left out = 2,000 lines on the paper. */
const TOOLS = 1994;
const LINES = 2000;
let record: { entries: Entry[]; text: string };

beforeAll(async () => {
  record = await makeRecord([{ id: "long-session", tools: TOOLS, outcome: "contradicted", summary: "A very long session." }]);
}, 60_000);

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(staticSite(demoText, record.text));
});
afterEach(() => vi.restoreAllMocks());

async function openLongSession() {
  render(<App />);
  await screen.findByRole("button", { name: /Cleared the build cache/ });
  fireEvent.click(screen.getByRole("button", { name: "How this was built" }));
  await screen.findByRole("button", { name: /A very long session/ });
  await within(screen.getByRole("status", { name: "Paper status" })).findByText("Paper intact", {}, { timeout: 30_000 });
}
const skip = () => screen.getByRole("button", { name: "Skip to end" });
const drawn = () => vi.mocked(entryText).mock.calls.length;

describe("a session with 2,000 lines", () => {
  it("has the lines the test says it has", () => {
    expect(record.entries.length + 1).toBe(LINES);
  });

  it("SKIP TO END prints every line at once and leaves the replay finished", async () => {
    await openLongSession();
    const paper = screen.getByRole("region", { name: "Printout" });
    expect(paper.querySelectorAll(".print-line--pending")).toHaveLength(LINES);
    expect(skip()).toBeEnabled();

    fireEvent.click(skip());

    expect(paper.querySelectorAll(".print-line--pending")).toHaveLength(0);
    expect(paper.querySelectorAll(".print-line")).toHaveLength(LINES);
    expect(document.querySelector(".lcd__state")).toHaveTextContent("Finished");
    expect(screen.getByRole("button", { name: "Play" })).toBeEnabled();
    expect(skip()).toBeDisabled(); // nothing left to print
    expect(screen.getByRole("button", { name: "Feed one line" })).toBeEnabled();
    // the overall verdict is the last line, stamped
    const last = paper.querySelectorAll(".print-line");
    expect(last[last.length - 1]).toHaveTextContent("CONTRADICTED");
    // and the clerk has something to say about it
    expect(screen.getByText(/doesn't match what the witness saw/)).toBeInTheDocument();
    // the paper still checks out
    expect(within(screen.getByRole("status", { name: "Paper status" })).getByText("Paper intact")).toBeInTheDocument();
  }, 60_000);

  it("picking a line redraws that line, not the other 1,999", async () => {
    await openLongSession();
    fireEvent.click(skip());
    const before = drawn();
    expect(before).toBeGreaterThanOrEqual(LINES - 1); // the skip drew them all

    fireEvent.click(screen.getByRole("button", { name: "Line 500: pick to tamper with" }));
    const first = drawn() - before;
    expect(first).toBeGreaterThan(0);
    expect(first).toBeLessThanOrEqual(3);

    const mid = drawn();
    fireEvent.click(screen.getByRole("button", { name: "Line 900: pick to tamper with" }));
    expect(drawn() - mid).toBeLessThanOrEqual(6); // the new pick and the old one
    expect(screen.getByRole("button", { name: "Line 900: picked to tamper with" })).toHaveAttribute("aria-pressed", "true");
  }, 60_000);

  it("feeding one line redraws the line just printed, not the ones before it", async () => {
    await openLongSession();
    const feed = screen.getByRole("button", { name: "Feed one line" });
    for (let i = 0; i < 150; i++) fireEvent.click(feed);
    const before = drawn();
    fireEvent.click(feed);
    expect(drawn() - before).toBeLessThanOrEqual(3);
    expect(document.querySelectorAll(".print-line--pending")).toHaveLength(LINES - 151);
  }, 60_000);

  it("the red circle still jumps to the witness line, however far away", async () => {
    await openLongSession();
    fireEvent.click(skip());
    const witness = record.entries.find((e) => e.kind === "witness" && e.data.event === "stop")!;
    fireEvent.click(screen.getByRole("button", { name: /Witness saw notes\.txt deleted/ }));
    expect(document.activeElement?.id).toBe(`line-${witness.seq}`);
  }, 60_000);

  it("tampering with a line deep in the paper tears the paper there", async () => {
    await openLongSession();
    fireEvent.click(skip());
    fireEvent.click(screen.getByRole("button", { name: "Line 1500: pick to tamper with" }));
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    await within(screen.getByRole("status", { name: "Paper status" })).findByText(
      "Paper torn at line 1500",
      {},
      { timeout: 30_000 },
    );
  }, 60_000);
});
