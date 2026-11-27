import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import type { Entry } from "../lib/chainCheck";
import { makeRecord, staticSite } from "./buildRecord";
import { BANNED, demoText, visibleLanguage } from "./demo";

let build: { entries: Entry[]; text: string };
let calls: string[];

beforeEach(async () => {
  build = await makeRecord([
    { id: "build-1", tools: 3, outcome: "supported", summary: "Wrote the recorder." },
    { id: "build-2", tools: 2, outcome: "contradicted", summary: "Tidied the folder." },
    { id: "build-3", tools: 2, outcome: "silent" },
    { id: "build-4", tools: 1, outcome: "unchecked", summary: "Started the printout." },
  ]);
});
afterEach(() => vi.restoreAllMocks());

function serve(buildText: string | null, metaText: string | null = null) {
  calls = [];
  const site = staticSite(demoText, buildText, metaText);
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    calls.push(String(input));
    return site(input);
  });
}

async function openDemo() {
  render(<App />);
  await screen.findByRole("button", { name: /Cleared the build cache/ });
  await within(screen.getByRole("status", { name: "Paper status" })).findByText("Paper intact");
}
async function openBuild() {
  await openDemo();
  fireEvent.click(screen.getByRole("button", { name: "How this was built" }));
  await screen.findByRole("button", { name: /Wrote the recorder/ });
}
const feed = () => screen.getByRole("button", { name: "Feed one line" });

describe("the switch on the page", () => {
  it("sits above the rolls, with Demo chosen first", async () => {
    serve(build.text);
    await openDemo();
    const group = screen.getByRole("group", { name: "Record to show" });
    expect(within(group).getByRole("button", { name: "Demo" })).toHaveAttribute("aria-pressed", "true");
    const firstRoll = screen.getByRole("button", { name: /Read main\.py/ });
    // document order is the tab order: the switch comes before the first roll
    expect(group.compareDocumentPosition(firstRoll) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.queryByText(/statements checked/)).toBeNull(); // totals belong to the other view
  });

  it("shows the build record's sessions as rolls with their real verdicts", async () => {
    serve(build.text);
    await openBuild();
    const nav = screen.getByRole("navigation", { name: "Sessions" });
    expect(within(nav).getByRole("button", { name: /Wrote the recorder/ })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: /Tidied the folder/ })).toBeInTheDocument();
    expect(within(nav).getByRole("button", { name: /No statement written/ })).toBeInTheDocument();
    expect(within(nav).queryByRole("button", { name: /Cleared the build cache/ })).toBeNull();
    const stamps = Array.from(nav.querySelectorAll(".stamp"), (s) => s.textContent);
    expect(stamps).toEqual(["SUPPORTED", "CONTRADICTED", "NO STATEMENT"]); // the unchecked one has no stamp
    expect(screen.getByRole("button", { name: "How this was built" })).toHaveAttribute("aria-pressed", "true");
  });

  it("writes the totals in plain words", async () => {
    serve(build.text);
    await openBuild();
    expect(
      screen.getByText(
        `4 sessions, ${build.entries.length} lines. 2 statements checked, 1 matched the evidence. 1 session changed files and said nothing. 1 statement was written and never checked.`,
      ),
    ).toBeInTheDocument();
  });

  it("opens on the contradicted session, and the printed paper is the build record's", async () => {
    serve(build.text);
    await openBuild();
    expect(screen.getByRole("button", { name: /Tidied the folder/ })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(feed());
    expect(document.getElementById(`line-${build.entries.find((e) => e.session_id === "build-2")!.seq}`)).not.toBeNull();
  });

  it("checks the paper with the record's own fingerprints", async () => {
    serve(build.text);
    await openBuild();
    await within(screen.getByRole("status", { name: "Paper status" })).findByText("Paper intact");
  });

  it("never calls the API and never polls in this view", async () => {
    serve(build.text);
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      await openBuild();
      const before = calls.length;
      await vi.advanceTimersByTimeAsync(10_000);
      expect(calls.length).toBe(before);
      expect(calls.slice(calls.findIndex((c) => c.includes("build-ledger"))).some((c) => c.includes("/api/"))).toBe(false);
      expect(screen.queryByText("LIVE")).toBeNull();
      expect(screen.queryByText("Check this statement")).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it("shows no word the page may not show", async () => {
    serve(build.text);
    await openBuild();
    expect(visibleLanguage()).not.toMatch(BANNED);
  });

  it("starts clean when the switch is changed", async () => {
    serve(build.text);
    await openBuild();
    fireEvent.click(screen.getByRole("button", { name: /Wrote the recorder/ }));
    fireEvent.click(feed());
    fireEvent.click(feed());
    fireEvent.click(screen.getAllByRole("button", { name: /^Line \d+: pick to tamper with/ })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    await within(screen.getByRole("status", { name: "Paper status" })).findByText(/Paper torn at line/);

    fireEvent.click(screen.getByRole("button", { name: "Demo" }));
    await screen.findByRole("button", { name: /Cleared the build cache/ });
    await within(screen.getByRole("status", { name: "Paper status" })).findByText("Paper intact");
    expect(screen.getByRole("button", { name: /Cleared the build cache/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Restore" })).toBeDisabled(); // nothing is tampered
    expect(document.querySelectorAll(".print-line--pending").length).toBeGreaterThan(0);
    expect(document.querySelectorAll(".print-line:not(.print-line--pending):not(.print-line--empty)").length).toBe(0);
    expect(document.querySelector(".print-line--tamper-target")).toBeNull();
  });

  it("comes back to the demo and asks the API again", async () => {
    serve(build.text);
    await openBuild();
    const before = calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Demo" }));
    await screen.findByRole("button", { name: /Read main\.py/ });
    expect(calls.slice(before).some((c) => c.includes("/api/ledger"))).toBe(true);
  });
});

describe("which part of the build the record covers", () => {
  // the generated record runs from 2026-03-01T09:00:01Z, one second per line
  it("says which dates it runs from and to, with no claim about the rest, when nobody said", async () => {
    serve(build.text);
    await openBuild();
    expect(screen.getByText("This record is from 1 March 2026.")).toBeInTheDocument();
    expect(screen.queryByText(/only part of the build/)).toBeNull();
  });

  it("says it covers only part of the build when the exporter said so", async () => {
    serve(build.text, '{"partial": true}');
    await openBuild();
    expect(
      await screen.findByText(
        "This record covers only part of the build: 1 March 2026. Earlier work was archived and is not shown here.",
      ),
    ).toBeInTheDocument();
    expect(visibleLanguage()).not.toMatch(BANNED);
  });

  it("does not claim a part when the exporter said the record is all of it", async () => {
    serve(build.text, '{"partial": false}');
    await openBuild();
    expect(screen.getByText("This record is from 1 March 2026.")).toBeInTheDocument();
    expect(screen.queryByText(/only part of the build/)).toBeNull();
  });

  it.each(["not json", '{"partial": "yes"}', "[]", ""])("ignores a meta file that says %j", async (meta) => {
    serve(build.text, meta);
    await openBuild();
    expect(screen.getByText("This record is from 1 March 2026.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows none of it in the demo view", async () => {
    serve(build.text, '{"partial": true}');
    await openDemo();
    expect(screen.queryByText(/This record/)).toBeNull();
  });
});

describe("when the build record is not there", () => {
  it.each([
    ["the file is missing", null],
    ["the file is not a record", "<!doctype html><html><body>app</body></html>"],
    ["the file is empty", ""],
  ])("%s: says so in plain words", async (_name, text) => {
    serve(text);
    await openDemo();
    fireEvent.click(screen.getByRole("button", { name: "How this was built" }));
    expect(await screen.findByText(/The build record has not been published yet/)).toBeInTheDocument();
    expect(screen.getByText(/The build record isn't published yet\. Click Demo to go back\./)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText(/statements checked/)).toBeNull();
    expect(visibleLanguage()).not.toMatch(BANNED);
    // and the way back works
    fireEvent.click(screen.getByRole("button", { name: "Demo" }));
    expect(await screen.findByRole("button", { name: /Read main\.py/ })).toBeInTheDocument();
    expect(screen.queryByText(/has not been published yet/)).toBeNull();
  });
});

describe("the switch can be used from the keyboard", () => {
  it("is reached by Tab before the rolls, and the chosen key is a pressed button", async () => {
    serve(build.text);
    await openDemo();
    const order = Array.from(document.querySelectorAll<HTMLElement>("button, a[href]")).filter(
      (el) => !el.closest('[aria-hidden="true"]'),
    );
    const at = (name: string | RegExp) => order.indexOf(screen.getByRole("button", { name }));
    expect(at("Demo")).toBeLessThan(at("How this was built"));
    expect(at("How this was built")).toBeLessThan(at(/Read main\.py/));
    await waitFor(() => expect(at("How this was built")).toBeGreaterThanOrEqual(0));
  });
});
