// API client for the Living PRD view (Lane C).
//
// Backend endpoints are being built in Lane B - until that lane lands these
// calls will return 404 in dev. The shapes here track the agreed contract
// from the Living-vision design doc; tests stub these functions directly.

import { fetchApi } from "@/services/api";
import type {
  LivingPrd,
  ResolveConflictPayload,
} from "@/types/livingPrd";

/**
 * Fetch a synthesized Living PRD for the given org.
 *
 * The orgId is part of the URL (the backend's tenant boundary) and also part
 * of the React Query key so caches don't leak between orgs after an org
 * switch. The signature mirrors the design-doc spec; callers should pull
 * orgId from useOrgContext() rather than localStorage.
 */
export async function getLivingPrd(
  id: string,
  orgId: string,
): Promise<LivingPrd> {
  if (!orgId) throw new Error("orgId is required");
  return fetchApi<LivingPrd>(`/api/orgs/${orgId}/living/prd/${id}`);
}

/**
 * Resolve a conflict on a Living PRD section. The mutation hook should
 * invalidate the PRD query on success so the section re-renders without the
 * conflict pill.
 */
export async function resolveConflict(
  prdId: string,
  conflictId: string,
  resolution: ResolveConflictPayload["resolution"],
  orgId: string,
): Promise<void> {
  if (!orgId) throw new Error("orgId is required");
  await fetchApi<void>(
    `/api/orgs/${orgId}/living/prd/${prdId}/conflicts/${conflictId}/resolve`,
    {
      method: "POST",
      body: JSON.stringify({ resolution } satisfies ResolveConflictPayload),
    },
  );
}
