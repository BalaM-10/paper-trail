import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Key } from "../components/Key";
import { Printer, type Light } from "../components/Printer";
import { ReplayControls } from "../components/ReplayControls";
import { TamperKeys } from "../components/TamperKeys";

describe("Printer", () => {
  it.each<Light>(["off", "ready", "busy", "error"])("draws the %s light", (light) => {
    const { container } = render(
      <Printer light={light} display={<span>hello</span>}>
        <button>k</button>
      </Printer>,
    );
    expect(container.firstElementChild).toHaveAttribute("data-light", light);
    const led = container.querySelector(".led")!;
    expect(led).toHaveClass(`led--${light}`);
    expect(led).toHaveAttribute("aria-hidden", "true"); // the display says it in words
  });

  it("holds the display and the keys, and a slot for the paper", () => {
    const { container } = render(
      <Printer light="ready" display={<span>Ready</span>}>
        <button>Play</button>
      </Printer>,
    );
    expect(container.querySelector(".lcd")).toHaveTextContent("Ready");
    expect(within(container.querySelector(".printer__keys") as HTMLElement).getByRole("button", { name: "Play" })).toBeTruthy();
    expect(container.querySelector(".printer__slot")).toHaveAttribute("aria-hidden", "true");
  });

  it("hides its decoration from assistive technology", () => {
    const { container } = render(
      <Printer light="off" display="x">
        <span />
      </Printer>,
    );
    expect(container.querySelector(".printer__lid")).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector(".printer__lid")).toHaveTextContent("PAPER TRAIL PT-1");
  });
});

describe("Key", () => {
  it("is a button that calls back, can stay down, and can be disabled", () => {
    const onClick = vi.fn();
    const { rerender } = render(<Key onClick={onClick}>Go</Key>);
    fireEvent.click(screen.getByRole("button", { name: "Go" }));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button")).not.toHaveAttribute("aria-pressed");

    rerender(<Key pressed>Go</Key>);
    expect(screen.getByRole("button")).toHaveAttribute("aria-pressed", "true");

    rerender(<Key disabled onClick={onClick}>Go</Key>);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("can carry a longer accessible name that contains the printed label", () => {
    render(
      <Key tone="red" label="Tamper with the paper">
        Tamper
      </Key>,
    );
    const key = screen.getByRole("button", { name: "Tamper with the paper" });
    expect(key).toHaveClass("key", "key--red");
    expect(key).toHaveTextContent("Tamper");
  });
});

describe("ReplayControls", () => {
  const setup = (over: Partial<Parameters<typeof ReplayControls>[0]> = {}) => {
    const handlers = { onPlay: vi.fn(), onPause: vi.fn(), onStep: vi.fn(), onSpeed: vi.fn() };
    render(<ReplayControls state="idle" speed={400} disabled={false} {...handlers} {...over} />);
    return handlers;
  };

  it("shows PLAY when stopped and PAUSE while printing", () => {
    const h = setup();
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(h.onPlay).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
  });

  it("PAUSE stops the printing", () => {
    const h = setup({ state: "playing" });
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(h.onPause).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("button", { name: "Play" })).toBeNull();
  });

  it("FEED goes one line", () => {
    const h = setup();
    fireEvent.click(screen.getByRole("button", { name: "Feed one line" }));
    expect(h.onStep).toHaveBeenCalledTimes(1);
  });

  it("holds down the chosen speed key and reports the others", () => {
    const h = setup({ speed: 100 });
    expect(screen.getByRole("button", { name: "Fast" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Normal" })).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(screen.getByRole("button", { name: "Slow" }));
    expect(h.onSpeed).toHaveBeenCalledWith(1000);
    fireEvent.click(screen.getByRole("button", { name: "Normal" }));
    expect(h.onSpeed).toHaveBeenCalledWith(400);
  });

  it("switches PLAY and FEED off when there is nothing to print", () => {
    setup({ disabled: true });
    expect(screen.getByRole("button", { name: "Play" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Feed one line" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Normal" })).toBeEnabled(); // speed can still be set
  });

  it("groups the keys with names", () => {
    setup();
    expect(screen.getByRole("group", { name: "Replay controls" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Speed" })).toBeInTheDocument();
  });
});

describe("TamperKeys", () => {
  it("has a red TAMPER key and a RESTORE key that call back", () => {
    const onTamper = vi.fn();
    const onRestore = vi.fn();
    render(<TamperKeys canTamper canRestore onTamper={onTamper} onRestore={onRestore} />);
    const tamper = screen.getByRole("button", { name: "Tamper with the paper" });
    expect(tamper).toHaveClass("key--red");
    fireEvent.click(tamper);
    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    expect(onTamper).toHaveBeenCalledTimes(1);
    expect(onRestore).toHaveBeenCalledTimes(1);
  });

  it("switches the keys off when they cannot be used", () => {
    render(<TamperKeys canTamper={false} canRestore={false} onTamper={() => {}} onRestore={() => {}} />);
    expect(screen.getByRole("button", { name: "Tamper with the paper" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Restore" })).toBeDisabled();
  });
});
