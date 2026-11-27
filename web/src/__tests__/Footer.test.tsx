import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Footer } from "../components/Footer";

describe("the repository link", () => {
  it("shows when the build was given a web address", () => {
    render(<Footer repoUrl="https://github.com/example/paper-trail" />);
    const link = screen.getByRole("link", { name: "View on GitHub" });
    expect(link).toHaveAttribute("href", "https://github.com/example/paper-trail");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
  });

  it.each(["#", "", "   ", "javascript:alert(1)", "example.org/repo", "ftp://example.org"])(
    "shows nothing for %j",
    (repoUrl) => {
      const { container } = render(<Footer repoUrl={repoUrl} />);
      expect(container).toBeEmptyDOMElement();
      expect(screen.queryByRole("link")).toBeNull();
    },
  );
});