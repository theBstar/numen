import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ConflictResolutionCard } from "../ConflictResolutionCard";
import type { Conflict } from "@/types/livingPrd";

const conflict: Conflict = {
  id: "c1",
  sources: [
    {
      tag: "notion#abc",
      value: "Launches Q2",
      queriedAt: new Date(Date.now() - 60_000).toISOString(),
    },
    {
      tag: "gdocs#xyz",
      value: "Launches Q3",
      queriedAt: new Date(Date.now() - 120_000).toISOString(),
    },
  ],
};

describe("ConflictResolutionCard", () => {
  it("renders both source claims", () => {
    render(<ConflictResolutionCard conflict={conflict} onResolve={vi.fn()} />);
    expect(screen.getByText("notion#abc")).toBeInTheDocument();
    expect(screen.getByText("gdocs#xyz")).toBeInTheDocument();
    expect(screen.getByText("Launches Q2")).toBeInTheDocument();
    expect(screen.getByText("Launches Q3")).toBeInTheDocument();
  });

  it("calls onResolve with pick_source when 'Use this source' is clicked", async () => {
    const onResolve = vi.fn();
    render(<ConflictResolutionCard conflict={conflict} onResolve={onResolve} />);
    const [firstButton] = screen.getAllByRole("button", { name: /use this source/i });
    if (!firstButton) throw new Error("button not found");
    await userEvent.click(firstButton);
    expect(onResolve).toHaveBeenCalledWith({
      kind: "pick_source",
      sourceTag: "notion#abc",
    });
  });

  it("calls onResolve with manual override", async () => {
    const onResolve = vi.fn();
    render(<ConflictResolutionCard conflict={conflict} onResolve={onResolve} />);
    const textarea = screen.getByLabelText(/manual override/i);
    await userEvent.type(textarea, "Launches in May");
    await userEvent.click(screen.getByRole("button", { name: /resolve with override/i }));
    expect(onResolve).toHaveBeenCalledWith({
      kind: "manual",
      value: "Launches in May",
    });
  });

  it("disables manual button when textarea is empty", () => {
    render(<ConflictResolutionCard conflict={conflict} onResolve={vi.fn()} />);
    expect(screen.getByRole("button", { name: /resolve with override/i })).toBeDisabled();
  });

  it("disables actions when isPending", () => {
    render(<ConflictResolutionCard conflict={conflict} onResolve={vi.fn()} isPending />);
    screen.getAllByRole("button", { name: /use this source/i }).forEach((b) => {
      expect(b).toBeDisabled();
    });
  });

  it("renders error message when provided", () => {
    render(
      <ConflictResolutionCard
        conflict={conflict}
        onResolve={vi.fn()}
        error="Resolve failed"
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Resolve failed");
  });
});
