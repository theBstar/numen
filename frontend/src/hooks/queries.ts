import { useQuery } from "@tanstack/react-query";
import * as api from "@/services/api";
import { useOrgContext } from "@/contexts/OrgContext";

export function useEntities(opts?: { type?: string; source?: string; pageSize?: number }) {
  const { orgId } = useOrgContext();
  const { type, source, pageSize } = opts ?? {};
  return useQuery({
    queryKey: ["entities", orgId, type, source, pageSize],
    queryFn: () => api.getEntities({ type, source, page_size: pageSize }).then((r) => r.items),
    enabled: !!orgId,
  });
}

export function useEntity(id: string) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["entity", orgId, id],
    queryFn: () => api.getEntity(id),
    enabled: !!orgId && !!id,
  });
}

export function useGoals() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["goals", orgId],
    queryFn: () => api.getGoals(),
    enabled: !!orgId,
  });
}

export function useGoalTree() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["goalTree", orgId],
    queryFn: () => api.getGoalTree(),
    enabled: !!orgId,
  });
}

export function useGoal(id: string) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["goal", orgId, id],
    queryFn: () => api.getGoal(id),
    enabled: !!orgId && !!id,
  });
}

export function useProjects() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["projects", orgId],
    queryFn: () => api.getProjects(),
    enabled: !!orgId,
  });
}

export function useProject(id: string) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["project", orgId, id],
    queryFn: () => api.getProject(id),
    enabled: !!orgId && !!id,
  });
}

export function useProjectTasks(id: string) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["projectTasks", orgId, id],
    queryFn: () => api.getProjectTasks(id),
    enabled: !!orgId && !!id,
  });
}

export function useTasks(filters?: Parameters<typeof api.getTasks>[0]) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["tasks", orgId, filters],
    queryFn: () => api.getTasks(filters),
    enabled: !!orgId,
  });
}

export function useTask(id: string) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["task", orgId, id],
    queryFn: () => api.getTask(id),
    enabled: !!orgId && !!id,
  });
}

export function useLatestBriefing() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["briefing", orgId],
    queryFn: () =>
      api.getLatestBriefing().catch((err) => {
        // 404 means no briefing yet - treat as empty, not error
        if (err?.status === 404) return null;
        throw err;
      }),
    enabled: !!orgId,
  });
}

export function useUrgency(limit?: number) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["urgency", orgId, limit],
    queryFn: () => api.getUrgency(limit),
    enabled: !!orgId,
  });
}

export function useMembers() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["members", orgId],
    queryFn: () => api.listMembers(),
    enabled: !!orgId,
  });
}

export function useConnectors() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["connectors", orgId],
    queryFn: () => api.getConnectorStatus(),
    enabled: !!orgId,
  });
}

export function useDashboardSummary() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["dashboardSummary", orgId],
    queryFn: () => api.getDashboardSummary(),
    enabled: !!orgId,
  });
}

export function useGitHubRepos() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["githubRepos", orgId],
    queryFn: () => api.getGitHubRepos(),
    enabled: !!orgId,
  });
}

export function useGraphNeighborhood(id: string, depth?: number) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["graph", orgId, id, depth],
    queryFn: () => api.getGraphNeighborhood(id, depth),
    enabled: !!orgId && !!id,
  });
}

export function useFullGraph(filters?: {
  entityTypes?: string[];
  edgeTypes?: string[];
  limit?: number;
  search?: string;
}) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["fullGraph", orgId, filters],
    queryFn: () =>
      api.getFullGraph({
        entity_types: filters?.entityTypes,
        edge_types: filters?.edgeTypes,
        limit: filters?.limit,
        search: filters?.search,
      }),
    enabled: !!orgId,
  });
}

export function useLinkSuggestions(status?: string, limit?: number) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["suggestions", orgId, status, limit],
    queryFn: () => api.getLinkSuggestions(status, limit),
    enabled: !!orgId,
  });
}

export function useApiKeys() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["apiKeys", orgId],
    queryFn: () => api.listApiKeys(),
    enabled: !!orgId,
  });
}

export function useOrgs() {
  return useQuery({
    queryKey: ["orgs"],
    queryFn: () => api.listOrgs(),
  });
}

export function useTaskActivity(taskId: string) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["taskActivity", orgId, taskId],
    queryFn: () => api.getTaskActivity(taskId),
    enabled: !!orgId && !!taskId,
  });
}

export function useSubtasks(taskId: string) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["subtasks", orgId, taskId],
    queryFn: () => api.getSubtasks(taskId),
    enabled: !!orgId && !!taskId,
  });
}

export function useSavedViews() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["savedViews", orgId],
    queryFn: () => api.getSavedViews(),
    enabled: !!orgId,
  });
}

export function useKanbanSettings() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["kanbanSettings", orgId],
    queryFn: () => api.getKanbanSettings(),
    enabled: !!orgId,
  });
}

export function useSprints(status?: string) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["sprints", orgId, status],
    queryFn: () => api.getSprints(status),
    enabled: !!orgId,
  });
}

export function useSprint(id: string) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["sprint", orgId, id],
    queryFn: () => api.getSprint(id),
    enabled: !!orgId && !!id,
  });
}

export function useTemplates() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["templates", orgId],
    queryFn: () => api.getTemplates(),
    enabled: !!orgId,
  });
}

export function useNotifications() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["notifications", orgId],
    queryFn: () => api.getNotifications(),
    enabled: !!orgId,
    refetchInterval: 60000, // Poll every minute
  });
}

export function useUnreadNotificationCount() {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["notificationCount", orgId],
    queryFn: () => api.getUnreadNotificationCount(),
    enabled: !!orgId,
    refetchInterval: 30000, // Poll every 30s
  });
}

export function useAttachments(taskId: string) {
  const { orgId } = useOrgContext();
  return useQuery({
    queryKey: ["attachments", orgId, taskId],
    queryFn: () => api.getAttachments(taskId),
    enabled: !!orgId && !!taskId,
  });
}
