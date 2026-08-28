import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { AgentReadIndicator } from "../AgentReadIndicator";
import type { AgentRead } from "@/types/livingPrd";

describe("AgentReadIndicator", () => {
  it("renders nothing when reads is empty", () => {
    const { container } = render(<AgentReadIndicator reads={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the most recent read", () => {
    const now = Date.now();
    const reads: AgentRead[] = [
      {
        taskId: "old",
        agentId: "agent-a",
        when: new Date(now - 5 * 60_000).toISOString(),
        sectionsRead: ["s1"],
      },
      {
        taskId: "task42",
        agentId: "agent-b",
        when: new Date(now - 30_000).toISOString(),
        sectionsRead: ["s1"],
      },
    ];
    render(<AgentReadIndicator reads={reads} />);
    const indicator = screen.getByTestId("agent-read");
    expect(indicator).toHaveTextContent("Read by #task42");
    expect(indicator).toHaveTextContent("(+1)");
  });

  it("does not show the +N suffix for a single read", () => {
    const reads: AgentRead[] = [
      {
        taskId: "solo",
        agentId: "agent-a",
        when: new Date().toISOString(),
        sectionsRead: [],
      },
    ];
    render(<AgentReadIndicator reads={reads} />);
    expect(screen.getByTestId("agent-read")).not.toHaveTextContent("+");
  });
});
