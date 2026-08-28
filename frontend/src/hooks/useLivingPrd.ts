// TanStack Query hooks for the Living PRD view.
//
// Cache isolation: every query key includes orgId per the project rule in
// CLAUDE.md - this prevents cross-tenant cache leaks when the user switches
// orgs.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useOrgContext } from "@/contexts/OrgContext";
import {
  getLivingPrd,
  resolveConflict,
} from "@/api/livingPrd";
import type {
  ConflictResolutionChoice,
  LivingPrd,
} from "@/types/livingPrd";

export function livingPrdQueryKey(orgId: string, prdId: string | undefined) {
  return ["livingPrd", orgId, prdId] as const;
}

export function useLivingPrd(prdId: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery<LivingPrd>({
    queryKey: livingPrdQueryKey(orgId, prdId),
    queryFn: () => getLivingPrd(prdId!, orgId),
    enabled: !!orgId && !!prdId,
  });
}

export interface ResolveConflictArgs {
  prdId: string;
  conflictId: string;
  resolution: ConflictResolutionChoice;
}

export function useResolveConflict() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ prdId, conflictId, resolution }: ResolveConflictArgs) =>
      resolveConflict(prdId, conflictId, resolution, orgId),
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: livingPrdQueryKey(orgId, vars.prdId) });
    },
  });
}
