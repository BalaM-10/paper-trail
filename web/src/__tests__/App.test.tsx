import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import {
  BANNED,
  SESSION_A,
  SESSION_B,
  commandSeq,
  demoEntries,
  demoText,
  ok,
  sessionOf,
  visibleLanguage,
  witnessStopSeq,
} from "./demo";

/** No API: the app falls back to the static demo ledger. */
function useDemoOnly() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input).includes("/api/")) throw new TypeError("no server");
    return ok(demoText);
  });
}

const sessionBLines = () => sessionOf(SESSION_B).length + 1; // + the "not mentioned" line

async function openDemo() {
  render(<App />);
  const spool = await screen.findByRole("button", { name: /Cleared the build cache/ });
  const status = screen.getByRole("status", { name: "Paper status" });
  await within(status).findByText("Paper intact");
  return { spool, status, paper: screen.getByRole("region", { name: "Printout" }) };
}

const feed = () => screen.getByRole("button", { name: "Feed one line" });

function stepTo(count: number) {
  for (let i = 0; i < count; i++) fireEvent.click(feed());
}

beforeEach(useDemoOnly);
afterEach(() => vi.restoreAllMocks());

describe("first load in demo mode", () => {
  it("shows the product name, the question, the explanation and the repository link", async () => {
    await openDemo();
    expect(screen.getByText("Paper Trail")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Did the agent do what it said?" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Pick a roll of paper, press PLAY/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View on GitHub" })).toHaveAttribute("href");
  });

  it("preselects the CONTRADICTED session and titles the rolls by summary", async () => {
    const { spool } = await openDemo();
    expect(spool).toHaveAttribute("aria-pressed", "true");
    const other = screen.getByRole("button", { name: /Read main\.py and wrote a notes file/ });
    expect(other).toHaveAttribute("aria-pressed", "false");
  });

  it("starts with blank paper and a marker on the first line", async () => {
    const { paper } = await openDemo();
    const rows = within(paper).queryAllByRole("listitem");
    expect(rows).toHaveLength(0); // unprinted lines are hidden from the page's structure
    expect(paper.querySelectorAll(".print-line--pending")).toHaveLength(sessionBLines());
    expect(paper.querySelectorAll(".print-line--next")).toHaveLength(1);
  });

  it("starts at Normal speed", async () => {
    await openDemo();
    expect(screen.getByRole("button", { name: "Normal" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Slow" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "Fast" })).toHaveAttribute("aria-pressed", "false");
  });

  it("never offers 'Check this statement' and never shows LIVE", async () => {
    await openDemo();
    expect(screen.queryByText("Check this statement")).toBeNull();
    expect(screen.queryByText("LIVE")).toBeNull();
  });
});

describe("the printer's front panel", () => {
  it("has every key, labelled, and the status light agrees with the display", async () => {
    await openDemo();
    for (const name of [
      "Play",
      "Feed one line",
      "Slow",
      "Normal",
      "Fast",
      "Tamper with the paper",
      "Restore",
      "Tear off report",
    ]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    const printer = document.querySelector(".printer")!;
    expect(printer).toHaveAttribute("data-light", "ready");
    expect(printer.querySelector(".led")).toHaveClass("led--ready");
    expect(printer.querySelector(".lcd__state")).toHaveTextContent("Ready");
  });

  it("changes the speed key that is held down", async () => {
    await openDemo();
    fireEvent.click(screen.getByRole("button", { name: "Fast" }));
    expect(screen.getByRole("button", { name: "Fast" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Normal" })).toHaveAttribute("aria-pressed", "false");
  });

  it("PLAY becomes PAUSE while printing, and the light turns amber", async () => {
    await openDemo();
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(await screen.findByRole("button", { name: "Pause" })).toBeInTheDocument();
    const printer = document.querySelector(".printer")!;
    expect(printer.querySelector(".led")).toHaveClass("led--busy");
    expect(printer.querySelector(".lcd__state")).toHaveTextContent("Printing");
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(await screen.findByRole("button", { name: "Play" })).toBeInTheDocument();
    expect(printer.querySelector(".lcd__state")).toHaveTextContent("Paused");
  });

  it("lights red and says Jammed when the paper is torn", async () => {
    const { status } = await openDemo();
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    await within(status).findByText(/Paper torn at line/);
    const printer = document.querySelector(".printer")!;
    expect(printer).toHaveAttribute("data-light", "error");
    expect(printer.querySelector(".led")).toHaveClass("led--error");
    expect(printer.querySelector(".lcd__state")).toHaveTextContent("Jammed");
  });
});

describe("replay to the end", () => {
  it("stamps CONTRADICTED and prints the undeclared line for sample/notes.txt", async () => {
    const { paper } = await openDemo();
    expect(within(paper).queryByText("CONTRADICTED")).toBeNull();

    stepTo(sessionBLines());

    expect(within(paper).getByText("CONTRADICTED")).toBeInTheDocument();
    expect(
      within(paper).getByText("Witness saw sample/notes.txt deleted. The agent never mentioned it."),
    ).toBeInTheDocument();
  });

  it("reads each verdict as a sentence that cites the witness line", async () => {
    const { paper } = await openDemo();
    stepTo(sessionBLines());
    const evidence = witnessStopSeq(SESSION_B);
    expect(
      within(paper).getByText(
        `Agent said it deleted sample/cache/output.bin. Witness agrees (line ${evidence}).`,
      ),
    ).toBeInTheDocument();
    expect(
      within(paper).getByRole("button", { name: new RegExp(`^Line ${evidence}:`) }),
    ).toBeInTheDocument();
  });

  it("prints the undeclared line after the verdicts and the overall verdict last", async () => {
    const { paper } = await openDemo();
    stepTo(sessionBLines());

    const rows = within(paper).getAllByRole("listitem");
    expect(rows).toHaveLength(sessionBLines());
    const [perPath, undeclared, overall] = rows.slice(-3);
    expect(perPath).toHaveTextContent("Agent said it deleted sample/cache/output.bin.");
    expect(perPath).toHaveTextContent("SUPPORTED");
    expect(undeclared).toHaveTextContent("The agent never mentioned it.");
    expect(overall).toHaveTextContent("Overall: the statement does not match the evidence.");
    expect(overall).toHaveTextContent("CONTRADICTED"); // the overall stamp is on the last line
  });

  it("reads the SUPPORTED session as sentences too, a file read checked against the record", async () => {
    const { paper } = await openDemo();
    fireEvent.click(screen.getByRole("button", { name: /Read main\.py and wrote a notes file/ }));
    stepTo(sessionOf(SESSION_A).length);
    const readTool = sessionOf(SESSION_A).find((e) => e.data.tool_name === "read_file")!;
    const stop = witnessStopSeq(SESSION_A);
    expect(
      within(paper).getByText(`Agent said it read src/main.py. The record agrees (line ${readTool.seq}).`),
    ).toBeInTheDocument();
    expect(
      within(paper).getByText(`Agent said it created docs/notes.md. Witness agrees (line ${stop}).`),
    ).toBeInTheDocument();
    expect(within(paper).getByText("Overall: the statement matches the evidence.")).toBeInTheDocument();
  });

  it("makes the overall stamp the biggest, with per-line stamps smaller", async () => {
    const { paper } = await openDemo();
    stepTo(sessionBLines());
    expect(within(paper).getByText("CONTRADICTED")).toHaveClass("stamp--huge");
    expect(within(paper).getByText("SUPPORTED")).toHaveClass("stamp--medium");
    // the rolls carry the small ones
    const nav = screen.getByRole("navigation", { name: "Sessions" });
    expect(within(nav).getByText("CONTRADICTED")).toHaveClass("stamp--small");
  });

  it("links the undeclared line to the witness line that proves it", async () => {
    const { paper } = await openDemo();
    stepTo(sessionBLines());
    fireEvent.click(within(paper).getByRole("button", { name: /Witness saw sample\/notes\.txt deleted/ }));
    expect(document.activeElement).toBe(document.getElementById(`line-${witnessStopSeq(SESSION_B)}`));
  });

  it("draws a marker arrow from the undeclared line (its length needs a real layout)", async () => {
    const { paper } = await openDemo();
    stepTo(sessionBLines());
    expect(paper.querySelectorAll(".marker-arrow")).toHaveLength(1);
    expect(paper.querySelectorAll(".undeclared-circle__ring")).toHaveLength(1);
  });
});

describe("printing animation", () => {
  it("only the line that has just printed is marked fresh", async () => {
    const { paper } = await openDemo();
    fireEvent.click(feed());
    await waitFor(() => expect(paper.querySelectorAll(".print-line--fresh")).toHaveLength(1));
    const first = sessionOf(SESSION_B)[0].seq;
    expect(document.getElementById(`line-${first}`)).toHaveClass("print-line--fresh");

    fireEvent.click(feed());
    await waitFor(() => {
      expect(paper.querySelectorAll(".print-line--fresh")).toHaveLength(1);
      expect(document.getElementById(`line-${first}`)).not.toHaveClass("print-line--fresh");
    });
  });

  it("gives every printed line its own ink density", async () => {
    const { paper } = await openDemo();
    stepTo(sessionBLines());
    const densities = Array.from(paper.querySelectorAll<HTMLElement>(".print-line:not(.print-line--pending)")).map(
      (li) => Number(li.style.getPropertyValue("--density")),
    );
    expect(densities).toHaveLength(sessionBLines());
    densities.forEach((d) => {
      expect(d).toBeGreaterThanOrEqual(0.82);
      expect(d).toBeLessThanOrEqual(1);
    });
    expect(new Set(densities).size).toBeGreaterThan(2);
  });
});

describe("tamper and restore", () => {
  const pieces = () => document.querySelectorAll(".paper-piece");

  it("tampers with the cleanup command line by default, tears there, and RESTORE mends it", async () => {
    const { status } = await openDemo();
    const target = commandSeq(SESSION_B);

    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    expect(await within(status).findByText(`Paper torn at line ${target}`)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Paper torn here", hidden: true })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    expect(await within(status).findByText("Paper intact")).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "Paper torn here", hidden: true })).toBeNull();
  });

  it("splits the paper in two at the broken line, and joins it again", async () => {
    const { status } = await openDemo();
    const first = sessionOf(SESSION_B)[0].seq;
    const target = commandSeq(SESSION_B);
    expect(pieces()).toHaveLength(1);

    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    await within(status).findByText(/Paper torn at line/);

    const [upper, lower] = Array.from(pieces());
    expect(upper).toHaveClass("paper-piece--upper");
    expect(lower).toHaveClass("paper-piece--lower");
    expect(upper.contains(document.getElementById(`line-${first}`))).toBe(true);
    expect(lower.contains(document.getElementById(`line-${target}`))).toBe(true);
    expect(upper.contains(document.getElementById(`line-${target}`))).toBe(false);
    // the gap is between them, and it is the only thing named "torn"
    const gap = screen.getByRole("img", { name: "Paper torn here", hidden: true });
    expect(gap.previousElementSibling).toBe(upper);
    expect(gap.nextElementSibling).toBe(lower);

    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    await within(status).findByText("Paper intact");
    expect(pieces()).toHaveLength(1);
  });

  it("does not print anything again when the paper tears or mends", async () => {
    const { paper, status } = await openDemo();
    stepTo(sessionBLines());
    await waitFor(() => expect(paper.querySelectorAll(".print-line--fresh")).toHaveLength(1));
    const first = sessionOf(SESSION_B)[0].seq;
    const aboveTheTear = document.getElementById(`line-${first}`);

    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    await within(status).findByText(/Paper torn at line/);
    expect(paper.querySelectorAll(".print-line--fresh")).toHaveLength(0);
    expect(document.getElementById(`line-${first}`)).toBe(aboveTheTear); // not even rebuilt

    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    await within(status).findByText("Paper intact");
    expect(paper.querySelectorAll(".print-line--fresh")).toHaveLength(0);
  });

  it("does not split a session whose lines are not the broken one, but still says torn", async () => {
    const { status } = await openDemo();
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" })); // line in session B
    await within(status).findByText(/Paper torn at line/);

    fireEvent.click(screen.getByRole("button", { name: /Read main\.py and wrote a notes file/ }));
    expect(pieces()).toHaveLength(1);
    expect(screen.queryByRole("img", { name: "Paper torn here", hidden: true })).toBeNull();
    expect(within(status).getByText(/Paper torn at line/)).toBeInTheDocument();
  });

  it("tampers with the line the visitor clicked, and clicking again lets it go", async () => {
    const { status } = await openDemo();
    stepTo(2); // prints the first two lines of the session
    const first = sessionOf(SESSION_B)[0].seq;
    const lineButton = () => screen.getByRole("button", { name: new RegExp(`^Line ${first}:`) });

    fireEvent.click(lineButton());
    expect(lineButton()).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(lineButton());
    expect(lineButton()).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(lineButton());
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    expect(await within(status).findByText(`Paper torn at line ${first}`)).toBeInTheDocument();
  });

  it("keeps RESTORE switched off until something has been tampered with", async () => {
    await openDemo();
    expect(screen.getByRole("button", { name: "Restore" })).toBeDisabled();
  });

  it("keeps the replay position when tampering and restoring", async () => {
    const { paper, status } = await openDemo();
    stepTo(3);
    const printed = () => paper.querySelectorAll(".print-line:not(.print-line--pending)").length;
    expect(printed()).toBe(3);
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    await within(status).findByText(/Paper torn at line/);
    expect(printed()).toBe(3);
    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    await within(status).findByText("Paper intact");
    expect(printed()).toBe(3);
  });
});

describe("tear off report", () => {
  it("prints, and the report holds the evidence with the overall verdict last", async () => {
    const print = vi.spyOn(window, "print").mockImplementation(() => {});
    await openDemo();
    fireEvent.click(screen.getByRole("button", { name: "Tear off report" }));
    expect(print).toHaveBeenCalledTimes(1);

    const report = document.querySelector(".print-report") as HTMLElement;
    await waitFor(() => expect(report).toHaveTextContent("Paper intact"));
    expect(report).toHaveTextContent(`Session: ${SESSION_B}`);
    expect(report).toHaveTextContent("Statement: Cleared the build cache.");
    const evidence = witnessStopSeq(SESSION_B);
    expect(report).toHaveTextContent(
      `SUPPORTED: Agent said it deleted sample/cache/output.bin. Witness agrees (line ${evidence}).`,
    );
    expect(report).toHaveTextContent("Witness saw sample/notes.txt deleted. The agent never mentioned it.");
    const paragraphs = report.querySelectorAll("p");
    expect(paragraphs[paragraphs.length - 1]).toHaveTextContent(
      "Overall: the statement does not match the evidence. (CONTRADICTED)",
    );
  });

  it("reports the torn paper when it has been tampered with", async () => {
    await openDemo();
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    const report = document.querySelector(".print-report") as HTMLElement;
    await waitFor(() => expect(report).toHaveTextContent(`Paper torn at line ${commandSeq(SESSION_B)}`));
  });
});

describe("the ghost clerk in the app", () => {
  const clerk = () => screen.getByRole("complementary", { name: "Ghost clerk" });
  const expression = () => clerk().querySelector("svg")!.getAttribute("data-expression");

  it("sits on the printer's corner, above it, with his bubble to his left", async () => {
    await openDemo();
    const printer = document.querySelector(".printer")!;
    expect(clerk().nextElementSibling).toBe(printer);
    const [bubble, figure] = Array.from(clerk().children);
    expect(bubble).toHaveClass("ghost-clerk__message");
    expect(figure).toHaveClass("ghost-clerk__figure");
  });

  it("opens calm, inviting the visitor to press PLAY", async () => {
    await openDemo();
    expect(clerk()).toHaveTextContent("I've pre-loaded the interesting session. Press PLAY when ready.");
    expect(expression()).toBe("calm");
  });

  it("is alarmed when the replay ends on CONTRADICTED", async () => {
    await openDemo();
    stepTo(sessionBLines());
    expect(clerk()).toHaveTextContent("doesn't match what the witness saw");
    expect(expression()).toBe("alarmed");
  });

  it("is alarmed when the paper is torn and calm again after RESTORE", async () => {
    const { status } = await openDemo();
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    await within(status).findByText(/Paper torn at line/);
    expect(clerk()).toHaveTextContent("Someone's been at the paper");
    expect(expression()).toBe("alarmed");

    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    await within(status).findByText("Paper intact");
    expect(clerk()).not.toHaveTextContent("Someone's been at the paper");
    expect(expression()).toBe("calm");
  });

  it("stops saying the demo was preloaded once the visitor picks a session", async () => {
    await openDemo();
    fireEvent.click(screen.getByRole("button", { name: /Read main\.py and wrote a notes file/ }));
    expect(clerk()).toHaveTextContent("Press PLAY to start");
    expect(clerk()).not.toHaveTextContent("pre-loaded");
  });

  it("is pleased when a SUPPORTED session finishes", async () => {
    await openDemo();
    fireEvent.click(screen.getByRole("button", { name: /Read main\.py and wrote a notes file/ }));
    stepTo(10);
    expect(expression()).toBe("pleased");
    expect(clerk()).toHaveTextContent("Everything checks out");
  });
});

describe("plain language", () => {
  it("never shows the banned words, before, during and after a tamper", async () => {
    const { status } = await openDemo();
    expect(visibleLanguage()).not.toMatch(BANNED);
    stepTo(sessionBLines());
    expect(visibleLanguage()).not.toMatch(BANNED);
    fireEvent.click(screen.getByRole("button", { name: "Tamper with the paper" }));
    await within(status).findByText(/Paper torn at line/);
    expect(visibleLanguage()).not.toMatch(BANNED);
  });
});

describe("when the demo file is missing", () => {
  it("says so lightly but clearly", async () => {
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("offline"));
    render(<App />);
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The paper jammed");
    expect(alert).toHaveTextContent("reload the page");
    expect(alert.textContent).not.toMatch(BANNED);
  });
});

describe("live mode (the local API is running)", () => {
  /** The API has the records but session B's statement has not been checked yet. */
  function useLiveApi() {
    const unchecked = demoEntries.filter((e) => e.seq <= 12);
    let served = unchecked;
    const calls: string[] = [];
    vi.restoreAllMocks();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push(`${init?.method ?? "GET"} ${url}`);
      if (url === "/api/ledger") return ok(JSON.stringify(served));
      if (url === `/api/verify/${SESSION_B}/1` && init?.method === "POST") {
        served = demoEntries; // checking appends the verdict records
        return ok("{}");
      }
      throw new TypeError("unexpected " + url);
    });
    return calls;
  }

  it("shows LIVE and offers 'Check this statement' only for the unchecked session", async () => {
    useLiveApi();
    render(<App />);
    expect(await screen.findByText("LIVE")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Check this statement" })).toHaveLength(1);
  });

  it("checks the statement, reloads the records, and the stamp appears", async () => {
    const calls = useLiveApi();
    render(<App />);
    const check = await screen.findByRole("button", { name: "Check this statement" });
    const nav = screen.getByRole("navigation", { name: "Sessions" });
    expect(within(nav).queryByText("CONTRADICTED")).toBeNull();

    fireEvent.click(check);

    expect(await within(nav).findByText("CONTRADICTED")).toBeInTheDocument();
    expect(calls).toContain(`POST /api/verify/${SESSION_B}/1`);
    await waitFor(() => expect(screen.queryByRole("button", { name: "Check this statement" })).toBeNull());
  });

  it("does not preselect a session: the visitor picks one", async () => {
    useLiveApi();
    render(<App />);
    const spool = await screen.findByRole("button", { name: /Cleared the build cache/ });
    expect(spool).toHaveAttribute("aria-pressed", "false");
  });
});
