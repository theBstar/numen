import { useQuery } from "@tanstack/react-query";
import * as api from "@/services/api";
import { useOrgContext } from "@/contexts/OrgContext";

export function usePrds(params?: { status?: string; search?: string; node_type?: string }) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prds", orgId, params],
    queryFn: () => api.getPrds(params),
    enabled: !!orgId,
  });
}

export function usePrd(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prd", orgId, prdId],
    queryFn: () => api.getPrd(prdId!),
    enabled: !!orgId && !!prdId,
  });
}

export function usePrdBlocks(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prdBlocks", orgId, prdId],
    queryFn: () => api.getPrdBlocks(prdId!),
    enabled: !!orgId && !!prdId,
  });
}

export function usePrdTree() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prdTree", orgId],
    queryFn: () => api.getPrdTree(),
    enabled: !!orgId,
  });
}

export function usePrdVersions(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prdVersions", orgId, prdId],
    queryFn: () => api.getPrdVersions(prdId!),
    enabled: !!orgId && !!prdId,
  });
}

export function usePrdCoverage(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prdCoverage", orgId, prdId],
    queryFn: () => api.getPrdCoverage(prdId!),
    enabled: !!orgId && !!prdId,
  });
}

export function usePrdReferences(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prdReferences", orgId, prdId],
    queryFn: () => api.getPrdReferences(prdId!),
    enabled: !!orgId && !!prdId,
  });
}

export function usePrdComments(
  prdId: string | undefined,
  blockId?: string,
  resolved?: boolean,
) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prdComments", orgId, prdId, blockId, resolved],
    queryFn: () =>
      api.getComments(prdId!, {
        block_id: blockId,
        resolved,
      }),
    enabled: !!orgId && !!prdId,
  });
}

export function useBlockReactions(prdId: string | undefined, blockId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["blockReactions", orgId, prdId, blockId],
    queryFn: () => api.getBlockReactions(prdId!, blockId!),
    enabled: !!orgId && !!prdId && !!blockId,
  });
}

export function usePrdReviews(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prdReviews", orgId, prdId],
    queryFn: () => api.getReviews(prdId!),
    enabled: !!orgId && !!prdId,
  });
}

export function usePrdReviewSummary(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prdReviewSummary", orgId, prdId],
    queryFn: () => api.getReviewSummary(prdId!),
    enabled: !!orgId && !!prdId,
  });
}

export function usePrdStakeholders(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prdStakeholders", orgId, prdId],
    queryFn: () => api.getStakeholders(prdId!),
    enabled: !!orgId && !!prdId,
  });
}

export function useAiSuggestedReviewers(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["aiSuggestedReviewers", orgId, prdId],
    queryFn: () => api.aiSuggestReviewers(prdId!),
    enabled: !!orgId && !!prdId,
  });
}

export function usePrdAlignmentChecks(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["prdAlignmentChecks", orgId, prdId],
    queryFn: () => api.getAlignmentChecks(prdId!),
    enabled: !!orgId && !!prdId,
  });
}
