import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PaperRoll } from "../components/PaperRoll";

const lines = (ids: number[]) =>
  ids.map((n) => (
    <li key={n} id={`line-${n}`} className="print-line">
      line {n}
    </li>
  ));

const pieces = (c: HTMLElement) => Array.from(c.querySelectorAll(".paper-piece"));

describe("whole paper", () => {
  it("is one piece with every line, a perforation at each end and feed holes", () => {
    const { container } = render(<PaperRoll torn={false} upper={lines([1, 2, 3])} />);
    expect(screen.getByRole("region", { name: "Printout" })).toHaveClass("paper-roll--whole");
    const [piece] = pieces(container);
    expect(pieces(container)).toHaveLength(1);
    expect(piece).toHaveClass("paper-piece--whole");
    expect(piece.querySelectorAll("li")).toHaveLength(3);
    expect(piece.querySelectorAll('[role="separator"]')).toHaveLength(2);
    expect(piece.querySelectorAll(".tractor-holes")).toHaveLength(2);
    expect(screen.queryByRole("img", { name: "Paper torn here" })).toBeNull();
  });
});

describe("torn paper", () => {
  const torn = () => render(<PaperRoll torn upper={lines([1, 2])} lower={lines([3, 4, 5])} />);

  it("is two pieces with a gap between them", () => {
    const { container } = torn();
    const [upper, lower] = pieces(container);
    expect(screen.getByRole("region", { name: "Printout" })).toHaveClass("paper-roll--torn");
    expect(upper).toHaveClass("paper-piece--upper");
    expect(lower).toHaveClass("paper-piece--lower");
    const gap = screen.getByRole("img", { name: "Paper torn here" });
    expect(gap).toHaveClass("paper-gap");
    expect(gap.previousElementSibling).toBe(upper);
    expect(gap.nextElementSibling).toBe(lower);
  });

  it("puts the lines above the break in the upper piece and the rest in the lower", () => {
    const { container } = torn();
    const [upper, lower] = pieces(container);
    expect(Array.from(upper.querySelectorAll("li")).map((li) => li.id)).toEqual(["line-1", "line-2"]);
    expect(Array.from(lower.querySelectorAll("li")).map((li) => li.id)).toEqual(["line-3", "line-4", "line-5"]);
  });

  it("gives each piece its own feed holes, and perforates only the ends that are still paper", () => {
    const { container } = torn();
    const [upper, lower] = pieces(container);
    for (const piece of [upper, lower]) expect(piece.querySelectorAll(".tractor-holes")).toHaveLength(2);
    expect(upper.querySelectorAll('[role="separator"]')).toHaveLength(1); // the top only
    expect(lower.querySelectorAll('[role="separator"]')).toHaveLength(1); // the bottom only
    expect(upper.firstElementChild!.lastElementChild!.tagName).toBe("OL"); // torn edge, no perforation
  });

  it("can start with the very first line torn", () => {
    const { container } = render(<PaperRoll torn upper={[]} lower={lines([1, 2])} />);
    const [upper, lower] = pieces(container);
    expect(upper.querySelectorAll("li")).toHaveLength(0);
    expect(lower.querySelectorAll("li")).toHaveLength(2);
  });
});

describe("tearing and mending", () => {
  it("does not rebuild the lines above the tear", () => {
    const { container, rerender } = render(<PaperRoll torn={false} upper={lines([1, 2, 3, 4])} />);
    const before = container.querySelector("#line-1");
    expect(before).not.toBeNull();

    rerender(<PaperRoll torn upper={lines([1, 2])} lower={lines([3, 4])} />);
    expect(container.querySelector("#line-1")).toBe(before);
    expect(pieces(container)).toHaveLength(2);

    rerender(<PaperRoll torn={false} upper={lines([1, 2, 3, 4])} />);
    expect(container.querySelector("#line-1")).toBe(before);
    expect(pieces(container)).toHaveLength(1);
    expect(screen.queryByRole("img", { name: "Paper torn here" })).toBeNull();
  });
});
