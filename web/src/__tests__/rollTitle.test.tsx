import { fireEvent, render, screen } from "@testing-library/react";
import { SessionList } from "../components/SessionList";
import { SessionSpool } from "../components/SessionSpool";
import type { Roll } from "../lib/rolls";

/*
  A long title is cut to three lines by the stylesheet (see styles.test.ts); jsdom has no
  layout, so here we check what the cut must not take away: the whole title as the
  button's name and as the tooltip, the stamp inside the same button, and the keyboard.
*/

const LONG =
  "Rewrote the witness so that it skips every file the project's .gitignore ignores, added a " +
  "built-in list of cache folders for Python, Node and editors, and checked the result with " +
  "property tests that run on every push. ".repeat(3).trim();

function roll(title: string, overallVerdict: string | null = "CONTRADICTED"): Roll {
  return {
    key: "abcdef12#1",
    sessionId: "abcdef12-0000",
    number: 1,
    count: 1,
    turnStart: false,
    entries: [],
    title,
    date: "2026-01-02",
    overallVerdict,
    hasUnverifiedStatement: false,
    statementIndex: null,
  };
}

function renderSpool(title: string, onSelect = () => {}) {
  render(
    <ul>
      <SessionSpool meta={roll(title)} selected={false} source="demo" onSelect={onSelect} onVerified={() => {}} />
    </ul>,
  );
  return screen.getByRole("button", { name: /Rewrote|Cleared/ });
}

test("the whole title is the name of the roll, however long it is", () => {
  const button = renderSpool(LONG);
  expect(button).toHaveAccessibleName(expect.stringContaining(LONG));
});

test("the whole title is the tooltip", () => {
  renderSpool(LONG);
  expect(screen.getByTitle(LONG)).toHaveClass("spool__title");
  expect(screen.getByTitle(LONG)).toHaveTextContent(LONG);
});

test("the text is not cut in the page itself: the cut is made by the stylesheet", () => {
  renderSpool(LONG);
  expect(screen.getByTitle(LONG).textContent).toBe(LONG);
  expect(screen.getByTitle(LONG).textContent).not.toMatch(/\u2026|\.\.\.$/);
});

test("a short title is shown as it is", () => {
  const button = renderSpool("Cleared the build cache.");
  expect(button).toHaveTextContent("Cleared the build cache.");
  expect(screen.getByTitle("Cleared the build cache.")).toHaveTextContent(/^Cleared the build cache\.$/);
});

test("the stamp is inside the roll's button, after the title and the line of details", () => {
  const button = renderSpool(LONG);
  const stamp = screen.getByText("CONTRADICTED");
  expect(button).toContainElement(stamp);
  const title = screen.getByTitle(LONG);
  expect(title.compareDocumentPosition(stamp) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("a title with no spaces is still one piece of text in the roll", () => {
  const button = renderSpool(`Rewrote${"x".repeat(300)}`);
  expect(button).toHaveTextContent("x".repeat(300));
});

test("the roll is a real button: Tab reaches it, and a press selects it", () => {
  const picked: string[] = [];
  const button = renderSpool(LONG, () => picked.push("picked"));
  expect(button.tagName).toBe("BUTTON");
  expect(button).toHaveAttribute("type", "button");
  expect(button).not.toHaveAttribute("tabindex", "-1");
  button.focus();
  expect(button).toHaveFocus();
  fireEvent.click(button); // Enter and Space on a button arrive as a click
  expect(picked).toEqual(["picked"]);
});

test("in the list, every roll keeps its own title, tooltip and stamp", () => {
  const rolls = [roll(LONG), { ...roll("Cleared the build cache.", "SUPPORTED"), key: "zzzz#1", sessionId: "zzzz" }];
  render(<SessionList sessions={rolls} selected={null} source="demo" onSelect={() => {}} onVerified={() => {}} />);
  expect(screen.getAllByRole("button")).toHaveLength(2);
  expect(screen.getByTitle(LONG)).toBeInTheDocument();
  expect(screen.getByText("SUPPORTED")).toBeInTheDocument();
  expect(screen.getByText("CONTRADICTED")).toBeInTheDocument();
});
