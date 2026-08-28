import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { ProvenancePane } from "../ProvenancePane";
import type { LivingPrdSection } from "@/types/livingPrd";

const section: LivingPrdSection = {
  id: "s1",
  title: "Risks",
  body: "Body",
  sources: [
    { type: "notion", weight: 0.7 },
    { type: "slack", weight: 0.3 },
  ],
  confidence: 0.9,
  recentAgentReads: [
    {
      taskId: "task1",
      agentId: "agent-x",
      when: new Date().toISOString(),
      sectionsRead: ["s1"],
    },
  ],
};

describe("ProvenancePane", () => {
  it("shows empty hint when no section selected", () => {
    render(<ProvenancePane section={null} onResolveConflict={vi.fn()} />);
    expect(screen.getByTestId("provenance-empty")).toBeInTheDocument();
  });

  it("renders sources tab content for selected section", () => {
    render(<ProvenancePane section={section} onResolveConflict={vi.fn()} />);
    expect(screen.getByText("Risks")).toBeInTheDocument();
    expect(screen.getByTestId("sources-list")).toBeInTheDocument();
    expect(screen.getByText(/notion/i)).toBeInTheDocument();
  });

  it("switches to agents tab and shows reads", async () => {
    render(<ProvenancePane section={section} onResolveConflict={vi.fn()} />);
    await userEvent.click(screen.getByRole("tab", { name: /agents/i }));
    expect(screen.getByTestId("agents-list")).toBeInTheDocument();
    expect(screen.getByText("#task1")).toBeInTheDocument();
  });

  it("renders conflict resolution card when section has a conflict", () => {
    render(
      <ProvenancePane
        section={{
          ...section,
          conflict: {
            id: "c1",
            sources: [
              { tag: "n#1", value: "v1", queriedAt: new Date().toISOString() },
              { tag: "g#1", value: "v2", queriedAt: new Date().toISOString() },
            ],
          },
        }}
        onResolveConflict={vi.fn()}
      />,
    );
    expect(screen.getByTestId("conflict-card")).toBeInTheDocument();
  });
});
