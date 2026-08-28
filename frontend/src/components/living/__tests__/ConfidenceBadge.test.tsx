import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ConfidenceBadge } from "../ConfidenceBadge";

describe("ConfidenceBadge", () => {
  it("renders the value to two decimal places", () => {
    render(<ConfidenceBadge value={0.876} />);
    expect(screen.getByTestId("confidence-badge")).toHaveTextContent("0.88");
  });

  it("clamps values above 1", () => {
    render(<ConfidenceBadge value={1.5} />);
    expect(screen.getByTestId("confidence-badge")).toHaveTextContent("1.00");
  });

  it("clamps values below 0", () => {
    render(<ConfidenceBadge value={-0.3} />);
    expect(screen.getByTestId("confidence-badge")).toHaveTextContent("0.00");
  });

  it("uses high tone for values >= 0.8", () => {
    render(<ConfidenceBadge value={0.9} />);
    expect(screen.getByTestId("confidence-badge").className).toContain("emerald");
  });

  it("uses medium tone for values >= 0.5", () => {
    render(<ConfidenceBadge value={0.6} />);
    expect(screen.getByTestId("confidence-badge").className).toContain("amber");
  });

  it("uses low tone for values < 0.5", () => {
    render(<ConfidenceBadge value={0.2} />);
    expect(screen.getByTestId("confidence-badge").className).toContain("rose");
  });
});
