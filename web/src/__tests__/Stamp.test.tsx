import { render, screen } from "@testing-library/react";
import { Stamp } from "../components/Stamp";

test("SUPPORTED stamp carries the word and the green class", () => {
  const { container } = render(<Stamp verdict="SUPPORTED" />);
  expect(screen.getByText("SUPPORTED")).toBeInTheDocument();
  expect(container.firstChild).toHaveClass("stamp", "stamp--supported");
});

test("CONTRADICTED stamp carries the word and the red class", () => {
  const { container } = render(<Stamp verdict="CONTRADICTED" />);
  expect(screen.getByText("CONTRADICTED")).toBeInTheDocument();
  expect(container.firstChild).toHaveClass("stamp--contradicted");
});

test("UNVERIFIED stamp carries the word and the amber class", () => {
  const { container } = render(<Stamp verdict="UNVERIFIED" />);
  expect(screen.getByText("UNVERIFIED")).toBeInTheDocument();
  expect(container.firstChild).toHaveClass("stamp--unverified");
});

test("is small by default, and can be medium or huge", () => {
  const { container, rerender } = render(<Stamp verdict="SUPPORTED" />);
  expect(container.firstChild).toHaveClass("stamp--small");
  rerender(<Stamp verdict="SUPPORTED" size="medium" />);
  expect(container.firstChild).toHaveClass("stamp--medium");
  expect(container.firstChild).not.toHaveClass("stamp--small");
  rerender(<Stamp verdict="CONTRADICTED" size="huge" />);
  expect(container.firstChild).toHaveClass("stamp--huge", "stamp--contradicted");
});

test("an unknown verdict still prints its word, without a colour class", () => {
  const { container } = render(<Stamp verdict="MAYBE" size="medium" />);
  expect(screen.getByText("MAYBE")).toBeInTheDocument();
  expect((container.firstChild as HTMLElement).className).toBe("stamp stamp--medium");
});
