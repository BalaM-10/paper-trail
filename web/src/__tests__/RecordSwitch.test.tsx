import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RecordSwitch } from "../components/RecordSwitch";

describe("the switch between records", () => {
  it("is a named group of two real buttons", () => {
    render(<RecordSwitch view="demo" onChange={() => {}} />);
    const group = screen.getByRole("group", { name: "Record to show" });
    const buttons = group.querySelectorAll("button");
    expect(Array.from(buttons, (b) => b.textContent)).toEqual(["Demo", "How this was built"]);
    buttons.forEach((b) => {
      expect(b.tagName).toBe("BUTTON"); // Tab, Enter and Space work by themselves
      expect(b).not.toBeDisabled();
      expect(b.getAttribute("tabindex")).toBeNull();
    });
  });

  it("says which one is chosen", () => {
    const { rerender } = render(<RecordSwitch view="demo" onChange={() => {}} />);
    expect(screen.getByRole("button", { name: "Demo" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "How this was built" })).toHaveAttribute("aria-pressed", "false");
    rerender(<RecordSwitch view="build" onChange={() => {}} />);
    expect(screen.getByRole("button", { name: "Demo" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: "How this was built" })).toHaveAttribute("aria-pressed", "true");
  });

  it("reports the other choice, and says nothing when the chosen one is clicked again", () => {
    const onChange = vi.fn();
    render(<RecordSwitch view="demo" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Demo" }));
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "How this was built" }));
    expect(onChange).toHaveBeenCalledWith("build");
  });
});
