import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MarkerArrow } from "../components/MarkerArrow";

/** Where each line is, in pixels from the top, as a real layout would report it. */
let tops: Record<string, number>;

function paper(opts: { witness?: boolean } = {}) {
  const { witness = true } = opts;
  return render(
    <section className="paper-roll">
      <ol>
        {witness && <li id="line-5">the witness line</li>}
        <li id="line-6">another line</li>
        <li id="note">
          the undeclared line
          <MarkerArrow targetSeq={5} />
        </li>
      </ol>
    </section>,
  );
}

const arrow = (c: HTMLElement) => c.querySelector(".marker-arrow") as HTMLElement;
const drawing = (c: HTMLElement) => c.querySelector(".marker-arrow svg") as SVGElement | null;

beforeEach(() => {
  tops = { "line-5": 100, "line-6": 200, note: 300 };
  vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
    const top = tops[this.id] ?? 0;
    return { top, bottom: top + 20, height: 20, left: 0, right: 100, width: 100, x: 0, y: top, toJSON() {} } as DOMRect;
  });
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("the marker arrow", () => {
  it("runs from the line up to the witness line, as long as the distance between them", () => {
    const { container } = paper();
    // middle of the undeclared line (310) minus middle of the witness line (110)
    expect(arrow(container)).toHaveStyle({ height: "200px" });
    const svg = drawing(container)!;
    expect(svg.getAttribute("height")).toBe("200");
    expect(svg.querySelectorAll("path")).toHaveLength(2); // a stem and an arrowhead
  });

  it("is decoration: hidden from assistive technology", () => {
    const { container } = paper();
    expect(arrow(container)).toHaveAttribute("aria-hidden", "true");
  });

  it("measures again when the window changes size", () => {
    const { container } = paper();
    tops["note"] = 400;
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(arrow(container)).toHaveStyle({ height: "300px" });
  });

  it("measures again when the paper changes size, for example when it tears", () => {
    let notify: () => void = () => {};
    const disconnect = vi.fn();
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(cb: () => void) {
          notify = cb;
        }
        observe() {}
        disconnect = disconnect;
      },
    );
    const { container, unmount } = paper();
    expect(arrow(container)).toHaveStyle({ height: "200px" });

    tops["note"] = 350; // the paper tore and the lower piece moved
    act(() => notify());
    expect(arrow(container)).toHaveStyle({ height: "250px" });

    unmount();
    expect(disconnect).toHaveBeenCalled();
  });

  it("draws nothing when the witness line is not on the page", () => {
    const { container } = paper({ witness: false });
    expect(drawing(container)).toBeNull();
    expect(arrow(container)).toHaveStyle({ height: "0px" });
  });

  it("draws nothing when there is no layout, as in a test browser", () => {
    vi.restoreAllMocks(); // every rectangle is zero again
    const { container } = paper();
    expect(drawing(container)).toBeNull();
  });

  it("draws nothing when the lines are too close for an arrow to make sense", () => {
    tops["note"] = 110;
    const { container } = paper();
    expect(drawing(container)).toBeNull();
  });

  it("stops listening for resizes when it goes away", () => {
    const remove = vi.spyOn(window, "removeEventListener");
    const { unmount } = paper();
    unmount();
    expect(remove).toHaveBeenCalledWith("resize", expect.any(Function));
  });
});
