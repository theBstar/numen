import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "@/services/api";
import type { TaskResponse } from "@/types";
import { useOrgContext } from "@/contexts/OrgContext";
import { trackTaskCreatedFE } from "@/analytics/events";

export function useCreateGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createGoal,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["goals"] });
      qc.invalidateQueries({ queryKey: ["goalTree"] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useUpdateGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof api.updateGoal>[1] }) =>
      api.updateGoal(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["goals"] });
      qc.invalidateQueries({ queryKey: ["goalTree"] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useDeleteGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.deleteGoal,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["goals"] });
      qc.invalidateQueries({ queryKey: ["goalTree"] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createProject,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof api.updateProject>[1] }) =>
      api.updateProject(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.deleteProject,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["projects"] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useCreateTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createTask,
    onSuccess: (task: TaskResponse) => {
      trackTaskCreatedFE({ taskId: String(task.id), projectId: task.project_id ?? null });
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useUpdateTask() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof api.updateTask>[1] }) =>
      api.updateTask(id, data),
    onMutate: async ({ id, data }) => {
      // Cancel outgoing refetches so they don't overwrite our optimistic update
      await qc.cancelQueries({ queryKey: ["tasks"] });

      // Snapshot all matching task list caches for rollback
      const previousCaches: [readonly unknown[], TaskResponse[] | undefined][] = [];
      const matchingQueries = qc.getQueriesData<TaskResponse[]>({ queryKey: ["tasks"] });
      for (const [key, value] of matchingQueries) {
        previousCaches.push([key, value]);
        if (value) {
          qc.setQueryData<TaskResponse[]>(key, value.map((t) =>
            t.id === id ? { ...t, ...data } : t
          ));
        }
      }

      return { previousCaches };
    },
    onError: (_err, _vars, context) => {
      // Rollback all caches on error
      if (context?.previousCaches) {
        for (const [key, data] of context.previousCaches) {
          qc.setQueryData(key, data);
        }
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
      qc.invalidateQueries({ queryKey: ["task", orgId] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useCreateEdge() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: api.createEdge,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["entity", orgId] });
      qc.invalidateQueries({ queryKey: ["entities", orgId] });
      qc.invalidateQueries({ queryKey: ["task", orgId] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useDeleteEdge() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: api.deleteEdge,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["entity", orgId] });
      qc.invalidateQueries({ queryKey: ["entities", orgId] });
      qc.invalidateQueries({ queryKey: ["task", orgId] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useAcceptSuggestion() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({
      suggestionId,
      skipAutoTransition,
    }: {
      suggestionId: string;
      skipAutoTransition?: boolean;
    }) => api.acceptSuggestion(suggestionId, skipAutoTransition),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["entity", orgId] });
      qc.invalidateQueries({ queryKey: ["entities", orgId] });
      qc.invalidateQueries({ queryKey: ["suggestions", orgId] });
      qc.invalidateQueries({ queryKey: ["task", orgId] });
      qc.invalidateQueries({ queryKey: ["fullGraph"] });
    },
  });
}

export function useDismissSuggestion() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: api.dismissSuggestion,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["suggestions", orgId] });
    },
  });
}

export function useCreateApiKey() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (name: string) => api.createApiKey(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["apiKeys", orgId] });
    },
  });
}

export function useRevokeApiKey() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: (keyId: string) => api.revokeApiKey(keyId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["apiKeys", orgId] });
    },
  });
}

export function useCreateOrg() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ name, slug }: { name: string; slug: string }) =>
      api.createOrg(name, slug),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["orgs"] }),
  });
}

export function useAddComment() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ taskId, content }: { taskId: string; content: string }) =>
      api.addComment(taskId, content),
    onSuccess: (_, { taskId }) => {
      qc.invalidateQueries({ queryKey: ["taskActivity", orgId, taskId] });
    },
  });
}

export function useEditComment() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ taskId, commentId, content }: { taskId: string; commentId: string; content: string }) =>
      api.editComment(taskId, commentId, content),
    onSuccess: (_, { taskId }) => {
      qc.invalidateQueries({ queryKey: ["taskActivity", orgId, taskId] });
    },
  });
}

export function useDeleteComment() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ taskId, commentId }: { taskId: string; commentId: string }) =>
      api.deleteComment(taskId, commentId),
    onSuccess: (_, { taskId }) => {
      qc.invalidateQueries({ queryKey: ["taskActivity", orgId, taskId] });
    },
  });
}

export function useCreateSubtask() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ taskId, data }: { taskId: string; data: Parameters<typeof api.createSubtask>[1] }) =>
      api.createSubtask(taskId, data),
    onSuccess: (_, { taskId }) => {
      qc.invalidateQueries({ queryKey: ["subtasks", orgId, taskId] });
      qc.invalidateQueries({ queryKey: ["task", orgId, taskId] });
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

export function useCreateSavedView() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createSavedView,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["savedViews"] });
    },
  });
}

export function useUpdateSavedView() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<import("@/types").SavedView> }) =>
      api.updateSavedView(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["savedViews"] });
    },
  });
}

export function useDeleteSavedView() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.deleteSavedView,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["savedViews"] });
    },
  });
}

export function useUpdateKanbanSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.updateKanbanSettings,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kanbanSettings"] });
    },
  });
}

export function useCreateSprint() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createSprint,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sprints"] });
    },
  });
}

export function useUpdateSprint() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      api.updateSprint(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sprints"] });
    },
  });
}

export function useAddTasksToSprint() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ sprintId, taskIds }: { sprintId: string; taskIds: string[] }) =>
      api.addTasksToSprint(sprintId, taskIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["sprints"] });
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

export function useCreateTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.createTemplate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["templates"] });
    },
  });
}

export function useDeleteTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.deleteTemplate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["templates"] });
    },
  });
}

export function useApplyTemplate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.applyTemplate,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.markNotificationRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
      qc.invalidateQueries({ queryKey: ["notificationCount"] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.markAllNotificationsRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
      qc.invalidateQueries({ queryKey: ["notificationCount"] });
    },
  });
}

export function useUploadAttachment() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ taskId, file }: { taskId: string; file: File }) =>
      api.uploadAttachment(taskId, file),
    onSuccess: (_, { taskId }) => {
      qc.invalidateQueries({ queryKey: ["attachments", orgId, taskId] });
    },
  });
}

export function useDeleteAttachment() {
  const qc = useQueryClient();
  const { orgId } = useOrgContext();
  return useMutation({
    mutationFn: ({ taskId, attachmentId }: { taskId: string; attachmentId: string }) =>
      api.deleteAttachment(taskId, attachmentId),
    onSuccess: (_, { taskId }) => {
      qc.invalidateQueries({ queryKey: ["attachments", orgId, taskId] });
    },
  });
}
