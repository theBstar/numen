import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/services/api";
import { useOrgContext } from "@/contexts/OrgContext";
import type { WikiFeatureUpdateRequest } from "@/types";

export function useWikiLanding() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["wiki", orgId],
    queryFn: () => api.getWikiLanding(),
    enabled: !!orgId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useWikiFeature(slug: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["wikiFeature", orgId, slug],
    queryFn: () => api.getWikiFeature(slug!),
    enabled: !!orgId && !!slug,
  });
}

export function useWikiConcept(slug: string | undefined) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["wikiConcept", orgId, slug],
    queryFn: () => api.getWikiConcept(slug!),
    enabled: !!orgId && !!slug,
  });
}

export function useWikiGraph() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["wikiGraph", orgId],
    queryFn: () => api.getWikiGraph(),
    enabled: !!orgId,
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateWikiFeature() {
  const { orgId } = useOrgContext();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ slug, data }: { slug: string; data: WikiFeatureUpdateRequest }) =>
      api.updateWikiFeature(slug, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["wikiFeature", orgId, variables.slug] });
      queryClient.invalidateQueries({ queryKey: ["wiki", orgId] });
    },
  });
}

export function useGenerateWiki() {
  const { orgId } = useOrgContext();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.generateWiki(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["wiki", orgId] });
      queryClient.invalidateQueries({ queryKey: ["wikiFeature", orgId] });
      queryClient.invalidateQueries({ queryKey: ["wikiConcept", orgId] });
      queryClient.invalidateQueries({ queryKey: ["wikiGraph", orgId] });
    },
  });
}
