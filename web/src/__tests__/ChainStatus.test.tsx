import { render, screen } from "@testing-library/react";
import { ChainStatus } from "../components/ChainStatus";

test("intact paper says so", () => {
  render(<ChainStatus ok={true} />);
  expect(screen.getByText("Paper intact")).toBeInTheDocument();
});

test("torn paper names the line", () => {
  render(<ChainStatus ok={false} brokenAt={3} />);
  expect(screen.getByText("Paper torn at line 3")).toBeInTheDocument();
});
