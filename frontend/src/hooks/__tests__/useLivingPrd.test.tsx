import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useLivingPrd, useResolveConflict } from "../useLivingPrd";
import type { LivingPrd } from "@/types/livingPrd";

// Mock the API client and the OrgContext so the hook can run in isolation.
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

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return {
    client,
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    ),
  };
}

const fixture: LivingPrd = {
  id: "p1",
  title: "Passkey rollout",
  workspace: "Numen",
  lastSyncAt: new Date().toISOString(),
  readsToday: 4,
  connectionStatus: "connected",
  sections: [],
};

describe("useLivingPrd", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("fetches the PRD and includes orgId in the cache key", async () => {
    mockedGet.mockResolvedValue(fixture);
    const { wrapper, client } = makeWrapper();
    const { result } = renderHook(() => useLivingPrd("p1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(fixture);
    expect(mockedGet).toHaveBeenCalledWith("p1", "org-1");
    // Cache key includes orgId
    const keys = client.getQueryCache().getAll().map((q) => q.queryKey);
    expect(keys).toContainEqual(["livingPrd", "org-1", "p1"]);
  });

  it("does not fetch when prdId is undefined", async () => {
    mockedGet.mockResolvedValue(fixture);
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useLivingPrd(undefined), { wrapper });
    await waitFor(() => expect(result.current.fetchStatus).toBe("idle"));
    expect(mockedGet).not.toHaveBeenCalled();
  });

  it("surfaces 404 errors", async () => {
    const err = Object.assign(new Error("not found"), { status: 404 });
    mockedGet.mockRejectedValue(err);
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useLivingPrd("missing"), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect((result.current.error as { status?: number }).status).toBe(404);
  });
});

describe("useResolveConflict", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls the API and invalidates the PRD query on success", async () => {
    mockedResolve.mockResolvedValue(undefined);
    mockedGet.mockResolvedValue(fixture);
    const { wrapper, client } = makeWrapper();

    // Seed the cache with a Living PRD query.
    const queryRender = renderHook(() => useLivingPrd("p1"), { wrapper });
    await waitFor(() => expect(queryRender.result.current.isSuccess).toBe(true));
    const initialState = client.getQueryState(["livingPrd", "org-1", "p1"]);
    expect(initialState).toBeDefined();

    const { result } = renderHook(() => useResolveConflict(), { wrapper });
    await result.current.mutateAsync({
      prdId: "p1",
      conflictId: "c1",
      resolution: { kind: "pick_source", sourceTag: "notion#1" },
    });

    expect(mockedResolve).toHaveBeenCalledWith(
      "p1",
      "c1",
      { kind: "pick_source", sourceTag: "notion#1" },
      "org-1",
    );

    // Query was invalidated (re-fetch was triggered)
    expect(mockedGet).toHaveBeenCalledTimes(2);
  });

  it("surfaces mutation errors", async () => {
    mockedResolve.mockRejectedValue(new Error("boom"));
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useResolveConflict(), { wrapper });
    await expect(
      result.current.mutateAsync({
        prdId: "p1",
        conflictId: "c1",
        resolution: { kind: "manual", value: "x" },
      }),
    ).rejects.toThrow("boom");
  });
});
