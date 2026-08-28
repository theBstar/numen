import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { LivingPrdSectionCard } from "../LivingPrdSectionCard";
import type { LivingPrdSection } from "@/types/livingPrd";

const baseSection: LivingPrdSection = {
  id: "s1",
  title: "Goals",
  body: "## Reduce friction\nShip passkey login.",
  sources: [
    { type: "notion", weight: 0.6 },
    { type: "git", weight: 0.4 },
  ],
  confidence: 0.84,
  recentAgentReads: [],
};

describe("LivingPrdSectionCard", () => {
  it("renders title, body markdown, sources, and confidence", () => {
    render(
      <LivingPrdSectionCard
        section={baseSection}
        selected={false}
        onSelect={vi.fn()}
        onOpenConflict={vi.fn()}
      />,
    );
    expect(screen.getByRole("heading", { name: "Goals" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Reduce friction" })).toBeInTheDocument();
    expect(screen.getByTestId("source-stack")).toBeInTheDocument();
    expect(screen.getByTestId("confidence-badge")).toHaveTextContent("0.84");
  });

  it("calls onSelect when clicked", async () => {
    const onSelect = vi.fn();
    render(
      <LivingPrdSectionCard
        section={baseSection}
        selected={false}
        onSelect={onSelect}
        onOpenConflict={vi.fn()}
      />,
    );
    await userEvent.click(screen.getByTestId("section-s1"));
    expect(onSelect).toHaveBeenCalled();
  });

  it("renders agent read indicator only when reads exist", () => {
    const { rerender } = render(
      <LivingPrdSectionCard
        section={baseSection}
        selected={false}
        onSelect={vi.fn()}
        onOpenConflict={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("agent-read")).not.toBeInTheDocument();

    rerender(
      <LivingPrdSectionCard
        section={{
          ...baseSection,
          recentAgentReads: [
            {
              taskId: "t1",
              agentId: "a1",
              when: new Date().toISOString(),
              sectionsRead: ["s1"],
            },
          ],
        }}
        selected={false}
        onSelect={vi.fn()}
        onOpenConflict={vi.fn()}
      />,
    );
    expect(screen.getByTestId("agent-read")).toBeInTheDocument();
  });

  it("renders conflict pill when section has a conflict and triggers callback", async () => {
    const onOpenConflict = vi.fn();
    render(
      <LivingPrdSectionCard
        section={{
          ...baseSection,
          conflict: {
            id: "c1",
            sources: [
              { tag: "n#1", value: "x", queriedAt: new Date().toISOString() },
              { tag: "g#1", value: "y", queriedAt: new Date().toISOString() },
            ],
          },
        }}
        selected={false}
        onSelect={vi.fn()}
        onOpenConflict={onOpenConflict}
      />,
    );
    await userEvent.click(screen.getByTestId("conflict-pill"));
    expect(onOpenConflict).toHaveBeenCalled();
  });

  it("marks selected with data-selected", () => {
    render(
      <LivingPrdSectionCard
        section={baseSection}
        selected
        onSelect={vi.fn()}
        onOpenConflict={vi.fn()}
      />,
    );
    expect(screen.getByTestId("section-s1")).toHaveAttribute("data-selected", "true");
  });
});
