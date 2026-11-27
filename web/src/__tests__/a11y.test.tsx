import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { SESSION_B, demoText, ok, sessionOf } from "./demo";

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    if (String(input).includes("/api/")) throw new TypeError("no server");
    return ok(demoText);
  });
});
afterEach(() => vi.restoreAllMocks());

async function openAndPrintEverything() {
  render(<App />);
  await screen.findByRole("button", { name: /Cleared the build cache/ });
  await within(screen.getByRole("status", { name: "Paper status" })).findByText("Paper intact");
  const feed = screen.getByRole("button", { name: "Feed one line" });
  for (let i = 0; i < sessionOf(SESSION_B).length + 1; i++) fireEvent.click(feed);
}

const INTERACTIVE = 'button, a[href], select, input, textarea, [role="button"], [tabindex]';

describe("keyboard and screen reader access", () => {
  it("every control is a real, named, focusable element", async () => {
    await openAndPrintEverything();
    const controls = Array.from(document.querySelectorAll<HTMLElement>(INTERACTIVE)).filter(
      // lines that have not printed yet are blank paper, hidden from everyone
      (el) => !el.closest('[aria-hidden="true"]'),
    );
    expect(controls.length).toBeGreaterThan(15);

    for (const el of controls) {
      const label = `${el.tagName.toLowerCase()} "${el.textContent?.trim().slice(0, 40)}"`;
      if (el.getAttribute("tabindex") === "-1") continue; // focus targets such as printed lines
      // Native elements are focusable and respond to Enter/Space by themselves.
      expect(["BUTTON", "A"], `${label} must be a native control`).toContain(el.tagName);
      expect(el, `${label} needs an accessible name`).toHaveAccessibleName();
    }
  });

  it("every key's accessible name contains its printed label", async () => {
    await openAndPrintEverything();
    const keys = Array.from(document.querySelectorAll<HTMLButtonElement>(".key"));
    expect(keys.length).toBe(8); // play, feed, three speeds, tamper, restore, tear off
    for (const key of keys) {
      const printed = key.textContent!.trim().toLowerCase();
      const name = (key.getAttribute("aria-label") ?? key.textContent!).toLowerCase();
      expect(name, `"${printed}" must be part of the name "${name}"`).toContain(printed);
    }
  });

  it("offers every action by its plain name", async () => {
    await openAndPrintEverything();
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
    expect(screen.getByRole("group", { name: "Speed" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Replay controls" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View on GitHub" })).toBeInTheDocument();
  });

  it("has the page landmarks and a single top-level heading", async () => {
    await openAndPrintEverything();
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("main")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Sessions" })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: "Ghost clerk" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("tabs through the rolls, then the printer's keys, then the paper", async () => {
    await openAndPrintEverything();
    const order = Array.from(document.querySelectorAll<HTMLElement>("button, a[href]")).filter(
      (el) => !el.closest('[aria-hidden="true"]'),
    );
    const index = (el: Element | null) => order.indexOf(el as HTMLElement);
    const roll = screen.getByRole("button", { name: /Cleared the build cache/ });
    const play = screen.getByRole("button", { name: "Play" });
    const tamper = screen.getByRole("button", { name: "Tamper with the paper" });
    const firstLine = screen.getAllByRole("button", { name: /^Line \d+:/ })[0];
    const link = screen.getByRole("link", { name: "View on GitHub" });
    expect(index(roll)).toBeLessThan(index(play));
    expect(index(play)).toBeLessThan(index(tamper));
    expect(index(tamper)).toBeLessThan(index(firstLine));
    expect(index(firstLine)).toBeLessThan(index(link));
  });

  it("reflects which session, speed and line are picked", async () => {
    await openAndPrintEverything();
    expect(screen.getByRole("button", { name: /Cleared the build cache/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Normal" })).toHaveAttribute("aria-pressed", "true");
    const lines = screen.getAllByRole("button", { name: /^Line \d+: pick to tamper with/ });
    expect(lines.length).toBe(sessionOf(SESSION_B).length);
    lines.forEach((line) => expect(line).toHaveAttribute("aria-pressed", "false"));
  });

  it("announces the paper status without taking focus", async () => {
    await openAndPrintEverything();
    const status = screen.getByRole("status", { name: "Paper status" });
    expect(status).toHaveTextContent("Paper intact");
  });

  it("hides the decoration from assistive technology", async () => {
    await openAndPrintEverything();
    const decor = [".led", ".printer__lid", ".printer__slot", ".tractor-holes", ".marker-arrow", ".spool__roll"];
    for (const selector of decor) {
      const found = document.querySelectorAll(selector);
      expect(found.length, selector).toBeGreaterThan(0);
      found.forEach((el) => expect(el.closest('[aria-hidden="true"]'), selector).not.toBeNull());
    }
  });

  it("verdicts always carry words, not colour alone", async () => {
    await openAndPrintEverything();
    const paper = screen.getByRole("region", { name: "Printout" });
    const stamps = paper.querySelectorAll(".stamp");
    expect(stamps.length).toBeGreaterThanOrEqual(2);
    stamps.forEach((s) => expect(s.textContent).toMatch(/^(SUPPORTED|CONTRADICTED|UNVERIFIED)$/));
  });
});
