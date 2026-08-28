import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";
import { LivingPrdView } from "../LivingPrdView";
import type { LivingPrd } from "@/types/livingPrd";

vi.mock("@/api/livingPrd", () => ({
  getLivingPrd: vi.fn(),
  resolveConflict: vi.fn(),
}));

vi.mock("@/contexts/OrgContext", () => ({
  useOrgContext: () => ({ orgId: "org-1", memberEmail: "x@y.z" }),
}));

import * as api from "@/api/livingPrd";

const mockedGet = vi.mocked(api.getLivingPrd);
const mockedResolve = vi.mocked(api.resolveConflict);

function makeFixture(overrides?: Partial<LivingPrd>): LivingPrd {
  return {
    id: "p1",
    title: "Passkey rollout",
    workspace: "Numen",
    lastSyncAt: new Date(Date.now() - 60_000).toISOString(),
    readsToday: 7,
    connectionStatus: "connected",
    sections: [
      {
        id: "s1",
        title: "Goals",
        body: "Reduce login friction.",
        sources: [
          { type: "notion", weight: 0.6 },
          { type: "git", weight: 0.4 },
        ],
        confidence: 0.85,
        recentAgentReads: [],
      },
      {
        id: "s2",
        title: "Risks",
        body: "Browser support.",
        sources: [
          { type: "gdocs", weight: 0.5 },
          { type: "slack", weight: 0.5 },
        ],
        confidence: 0.55,
        recentAgentReads: [],
        conflict: {
          id: "c1",
          sources: [
            { tag: "gdocs#1", value: "Q3", queriedAt: new Date().toISOString() },
            { tag: "slack#1", value: "Q4", queriedAt: new Date().toISOString() },
          ],
        },
      },
    ],
    ...overrides,
  };
}

function renderPage(prdId = "p1") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/prd/${prdId}`]}>
        <Routes>
          <Route path="/prd/:id" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(<LivingPrdView />, { wrapper });
}

describe("LivingPrdView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a loading state then the synthesized doc", async () => {
    mockedGet.mockImplementation(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve(makeFixture()), 10),
        ),
    );
    renderPage();
    expect(screen.getByTestId("living-prd-loading")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("living-prd-view")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Passkey rollout", level: 1 })).toBeInTheDocument();
    expect(screen.getByTestId("section-s1")).toBeInTheDocument();
    expect(screen.getByTestId("section-s2")).toBeInTheDocument();
    expect(screen.getByTestId("connection-status")).toHaveAttribute(
      "data-status",
      "connected",
    );
  });

  it("shows empty state when there are no sections", async () => {
    mockedGet.mockResolvedValue(makeFixture({ sections: [] }));
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("living-prd-empty")).toBeInTheDocument(),
    );
  });

  it("shows 404 error message when API returns 404", async () => {
    mockedGet.mockRejectedValue(Object.assign(new Error("nope"), { status: 404 }));
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("living-prd-error")).toHaveTextContent(/not found/i),
    );
  });

  it("shows generic error message for non-404 errors", async () => {
    mockedGet.mockRejectedValue(Object.assign(new Error("boom"), { status: 500 }));
    renderPage();
    await waitFor(() =>
      expect(screen.getByTestId("living-prd-error")).toHaveTextContent(/try again/i),
    );
  });

  it("selecting a section drives the right pane", async () => {
    mockedGet.mockResolvedValue(makeFixture());
    renderPage();
    await waitFor(() => expect(screen.getByTestId("section-s2")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("section-s2"));
    expect(screen.getByTestId("provenance-pane")).toHaveTextContent("Risks");
  });

  it("clicking the conflict pill opens the resolution card", async () => {
    mockedGet.mockResolvedValue(makeFixture());
    renderPage();
    await waitFor(() => expect(screen.getByTestId("section-s2")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("conflict-pill"));
    expect(screen.getByTestId("conflict-card")).toBeInTheDocument();
  });

  it("conflict resolution happy path calls the API and re-fetches", async () => {
    mockedGet.mockResolvedValue(makeFixture());
    mockedResolve.mockResolvedValue(undefined);
    renderPage();
    await waitFor(() => expect(screen.getByTestId("section-s2")).toBeInTheDocument());
    await userEvent.click(screen.getByTestId("conflict-pill"));
    const [firstUseButton] = await screen.findAllByRole("button", { name: /use this source/i });
    if (!firstUseButton) throw new Error("button not found");
    await userEvent.click(firstUseButton);
    await waitFor(() =>
      expect(mockedResolve).toHaveBeenCalledWith(
        "p1",
        "c1",
        { kind: "pick_source", sourceTag: "gdocs#1" },
        "org-1",
      ),
    );
    // Query invalidation triggers a re-fetch
    await waitFor(() => expect(mockedGet).toHaveBeenCalledTimes(2));
  });
});
