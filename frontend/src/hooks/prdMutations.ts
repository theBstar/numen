import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/services/api";
import { useOrgContext } from "@/contexts/OrgContext";
import type { CreatePrdPayload, UpdatePrdPayload, PrdBlockOperation, PrdReviewStatus } from "@/types";

export function useCreateComment(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (payload: { content: string; block_id?: string | null; parent_id?: string | null }) =>
      api.createComment(prdId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdComments", orgId, prdId] });
      qc.invalidateQueries({ queryKey: ["prd", orgId, prdId] });
    },
  });
}

export function useUpdateComment(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ commentId, content }: { commentId: string; content: string }) =>
      api.updateComment(prdId, commentId, { content }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdComments", orgId, prdId] });
    },
  });
}

export function useDeleteComment(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (commentId: string) => api.deletePrdComment(prdId, commentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdComments", orgId, prdId] });
      qc.invalidateQueries({ queryKey: ["prd", orgId, prdId] });
    },
  });
}

export function useResolveComment(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ commentId, resolve }: { commentId: string; resolve: boolean }) =>
      resolve ? api.resolveComment(prdId, commentId) : api.unresolveComment(prdId, commentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdComments", orgId, prdId] });
    },
  });
}

export function useToggleReaction(prdId: string, blockId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (emoji: string) => api.toggleReaction(prdId, blockId, emoji),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["blockReactions", orgId, prdId, blockId] });
    },
  });
}

export function useCreatePrd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreatePrdPayload) => api.createPrd(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prds"] });
      qc.invalidateQueries({ queryKey: ["prdTree"] });
    },
  });
}

export function useUpdatePrd() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdatePrdPayload }) =>
      api.updatePrd(id, data),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["prds"] });
      qc.invalidateQueries({ queryKey: ["prd", orgId, variables.id] });
      qc.invalidateQueries({ queryKey: ["prdTree"] });
    },
  });
}

export function useDeletePrd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (prdId: string) => api.deletePrd(prdId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prds"] });
      qc.invalidateQueries({ queryKey: ["prdTree"] });
    },
  });
}

export function useMovePrd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ prdId, parentId, position }: { prdId: string; parentId: string | null; position: number }) =>
      api.movePrd(prdId, parentId, position),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prds"] });
      qc.invalidateQueries({ queryKey: ["prdTree"] });
    },
  });
}

export function useSavePrdBlocks() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ prdId, operations }: { prdId: string; operations: PrdBlockOperation[] }) =>
      api.savePrdBlocks(prdId, operations),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["prdBlocks", orgId, variables.prdId] });
    },
  });
}

export function useCreatePrdVersion() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ prdId, message }: { prdId: string; message?: string }) =>
      api.createPrdVersion(prdId, message),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["prdVersions", orgId, variables.prdId] });
      qc.invalidateQueries({ queryKey: ["prd", orgId, variables.prdId] });
    },
  });
}

export function useTransitionPrdStatus() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ prdId, status }: { prdId: string; status: string }) =>
      api.transitionPrdStatus(prdId, status),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["prds"] });
      qc.invalidateQueries({ queryKey: ["prd", orgId, variables.prdId] });
      qc.invalidateQueries({ queryKey: ["prdTree"] });
      qc.invalidateQueries({ queryKey: ["prdReviewSummary", orgId, variables.prdId] });
    },
  });
}

export function useUploadPrdMedia() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: async ({
      prdId,
      file,
    }: {
      prdId: string;
      file: File;
    }) => {
      // Step 1: Get upload URL
      const { upload_url, storage_key } = await api.getUploadUrl(
        prdId,
        file.name,
        file.type,
      );

      // Step 2: Upload to S3
      await fetch(upload_url, {
        method: "PUT",
        headers: { "Content-Type": file.type },
        body: file,
      });

      // Step 3: Confirm upload
      return api.confirmUpload(prdId, storage_key, file.name, file.type, file.size);
    },
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["prd", orgId, variables.prdId] });
      qc.invalidateQueries({ queryKey: ["prdBlocks", orgId, variables.prdId] });
    },
  });
}

export function useAddReviewer(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (memberId: string) => api.addReviewer(prdId, memberId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdReviews", orgId, prdId] });
      qc.invalidateQueries({ queryKey: ["prdReviewSummary", orgId, prdId] });
      qc.invalidateQueries({ queryKey: ["prdStakeholders", orgId, prdId] });
    },
  });
}

export function useRemoveReviewer(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (memberId: string) => api.removeReviewer(prdId, memberId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdReviews", orgId, prdId] });
      qc.invalidateQueries({ queryKey: ["prdReviewSummary", orgId, prdId] });
      qc.invalidateQueries({ queryKey: ["prdStakeholders", orgId, prdId] });
    },
  });
}

export function useAddStakeholder(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (memberId: string) => api.addStakeholder(prdId, memberId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdStakeholders", orgId, prdId] });
    },
  });
}

export function useRemoveStakeholder(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (memberId: string) => api.removeStakeholder(prdId, memberId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdStakeholders", orgId, prdId] });
    },
  });
}

export function useSubmitReview(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (payload: { status: PrdReviewStatus; comment?: string | null }) =>
      api.submitReview(prdId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdReviews", orgId, prdId] });
      qc.invalidateQueries({ queryKey: ["prdReviewSummary", orgId, prdId] });
    },
  });
}

export function useImportPrd() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      source,
      sourceId,
      parentFolderId,
      baseUrl,
    }: {
      source: api.ImportSource;
      sourceId: string;
      parentFolderId?: string;
      baseUrl?: string;
    }) => api.importPrd(source, sourceId, parentFolderId, baseUrl),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prds"] });
      qc.invalidateQueries({ queryKey: ["prdTree"] });
    },
  });
}

export function useImportPrdFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, parentFolderId }: { file: File; parentFolderId?: string }) =>
      api.importPrdFile(file, parentFolderId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prds"] });
      qc.invalidateQueries({ queryKey: ["prdTree"] });
    },
  });
}

export function useImportPrdBulk() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      source,
      rootPageId,
      parentFolderId,
      baseUrl,
    }: {
      source: api.ImportSource;
      rootPageId: string;
      parentFolderId?: string;
      baseUrl?: string;
    }) => api.importPrdBulk(source, rootPageId, parentFolderId, baseUrl),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prds"] });
      qc.invalidateQueries({ queryKey: ["prdTree"] });
    },
  });
}

export function useAiCompletePrd(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (prompt: string) => api.aiCompletePrd(prdId, prompt),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdBlocks", orgId, prdId] });
    },
  });
}

export function useAiEditSection(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ blockIds, instruction }: { blockIds: string[]; instruction: string }) =>
      api.aiEditSection(prdId, blockIds, instruction),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdBlocks", orgId, prdId] });
    },
  });
}

export function useAcknowledgeFinding(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (checkId: string) => api.acknowledgeFinding(checkId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdAlignmentChecks", orgId, prdId] });
    },
  });
}

export function useResolveFinding(prdId: string) {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (checkId: string) => api.resolveFinding(checkId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdAlignmentChecks", orgId, prdId] });
    },
  });
}

export function useExportPrd() {
  return useMutation({
    mutationFn: async ({
      prdId,
      format,
      options,
    }: {
      prdId: string;
      format: api.ExportFormat;
      options?: Record<string, unknown>;
    }) => {
      const result = await api.exportPrd(prdId, format, options);

      // For file formats, trigger browser download
      if (result instanceof Blob) {
        const formatExtensions: Record<string, string> = {
          markdown: ".md",
          html: ".html",
          pdf: ".pdf",
        };
        const ext = formatExtensions[format] || "";
        const url = URL.createObjectURL(result);
        const link = document.createElement("a");
        link.href = url;
        link.download = `export${ext}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        return { downloaded: true };
      }

      // For API formats, return the URL
      return result;
    },
  });
}
