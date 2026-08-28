import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { SourceDotStack } from "../SourceDotStack";
import type { SourceDot } from "@/types/livingPrd";

describe("SourceDotStack", () => {
  it("renders one dot per source", () => {
    const sources: SourceDot[] = [
      { type: "notion", weight: 0.5 },
      { type: "git", weight: 0.3 },
    ];
    render(<SourceDotStack sources={sources} />);
    expect(screen.getByTestId("source-dot-notion")).toBeInTheDocument();
    expect(screen.getByTestId("source-dot-git")).toBeInTheDocument();
  });

  it("shows empty placeholder when sources is empty", () => {
    render(<SourceDotStack sources={[]} />);
    expect(screen.getByTestId("source-stack-empty")).toBeInTheDocument();
  });

  it("orders dots by descending weight", () => {
    const sources: SourceDot[] = [
      { type: "notion", weight: 0.1 },
      { type: "slack", weight: 0.9 },
      { type: "gdocs", weight: 0.5 },
    ];
    render(<SourceDotStack sources={sources} />);
    const stack = screen.getByTestId("source-stack");
    const dotTypes = Array.from(stack.querySelectorAll("[data-testid^='source-dot-']")).map(
      (el) => el.getAttribute("data-testid"),
    );
    expect(dotTypes).toEqual([
      "source-dot-slack",
      "source-dot-gdocs",
      "source-dot-notion",
    ]);
  });
});
