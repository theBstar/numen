import type {
  EntityListResponse,
  EntityDetailResponse,
  GoalResponse,
  GoalTreeNode,
  CreateGoalPayload,
  UpdateGoalPayload,
  ProjectResponse,
  TaskResponse,
  Briefing,
  UrgencyScore,
  ConnectorStatus,
  GraphNeighborhoodResponse,
  Edge,
  Organization,
  OrgMember,
  TaskActivity,
  SavedView,
  KanbanSettings,
  KanbanSettingItem,
  Sprint,
  TaskTemplate,
  AppNotification,
  Attachment,
  PrdResponse,
  PrdTreeNode,
  PrdBlockResponse,
  PrdBlockOperation,
  PrdVersionResponse,
  PrdMediaResponse,
  PrdReference,
  PrdCoverage,
  PrdReviewResponse,
  PrdReviewSummary,
  PrdStakeholderResponse,
  AlignmentCheckResponse,
  CreatePrdPayload,
  UpdatePrdPayload,
  PrdReviewStatus,
  TestBriefingResponse,
} from "@/types";

const API_BASE = import.meta.env.VITE_API_URL || "";

// Org context - hydrated synchronously at module load from localStorage so
// the first render after a hard reload already has _orgId populated. Without
// this, child hooks queue fetches before OrgContext's useEffect calls
// setOrgContext(), and orgPath() throws with "Org context not set".
const _readStoredEmail = (): string => {
  if (typeof localStorage === "undefined") return "";
  const direct = localStorage.getItem("numen_email");
  if (direct) return direct;
  try {
    return JSON.parse(localStorage.getItem("numen_user") || "{}").email || "";
  } catch {
    return "";
  }
};
let _orgId: string =
  (typeof localStorage !== "undefined" && localStorage.getItem("numen_org_id")) || "";
let _memberEmail: string = _readStoredEmail();

// JWT auth token
let _accessToken: string = "";

export function setAccessToken(token: string) {
  _accessToken = token;
}

export function getAccessToken(): string {
  return _accessToken;
}

export function setOrgContext(orgId: string, memberEmail: string) {
  _orgId = orgId;
  _memberEmail = memberEmail;
}

export function getOrgContext() {
  return { orgId: _orgId, memberEmail: _memberEmail };
}

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = localStorage.getItem("numen_refresh_token");
  if (!refreshToken) return false;
  try {
    const res = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    _accessToken = data.access_token;
    localStorage.setItem("numen_access_token", data.access_token);
    if (data.refresh_token) {
      localStorage.setItem("numen_refresh_token", data.refresh_token);
    }
    return true;
  } catch {
    return false;
  }
}

export { tryRefreshToken };

let _isRefreshing = false;

export async function fetchApi<T>(path: string, options?: RequestInit & { _retried?: boolean }): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string>),
  };

  // Use JWT Bearer token if available, fall back to X-Member-Email for dev mode
  if (_accessToken) {
    headers["Authorization"] = `Bearer ${_accessToken}`;
  } else if (_memberEmail) {
    headers["X-Member-Email"] = _memberEmail;
  }

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });

  // Auto-refresh on 401 (only once per request)
  if (response.status === 401 && !options?._retried && !_isRefreshing) {
    _isRefreshing = true;
    const refreshed = await tryRefreshToken();
    _isRefreshing = false;
    if (refreshed) {
      return fetchApi<T>(path, { ...options, _retried: true });
    }
    // Refresh failed - clear auth and redirect
    logout();
    throw new ApiError(401, "Session expired");
  }

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    // Fire-and-forget analytics; never block the error path.
    import("@/analytics")
      .then(({ analytics }) => {
        analytics.track("error.api_request_failed", {
          path,
          status: response.status,
          method: (options?.method || "GET").toUpperCase(),
        });
      })
      .catch(() => {});
    throw new ApiError(response.status, body.detail || `API error: ${response.status}`);
  }
  if (response.status === 204 || response.headers.get("content-length") === "0") {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function orgPath(path: string): string {
  if (!_orgId) throw new Error("Org context not set. Call setOrgContext() first.");
  return `/api/orgs/${_orgId}${path}`;
}

// ── Auth ──

export function logout() {
  // Dynamic import so services layer stays free of React-tree deps.
  import("@/analytics")
    .then(({ analytics }) => {
      analytics.track("auth.logged_out");
      analytics.reset();
    })
    .catch(() => {});
  localStorage.removeItem("numen_access_token");
  localStorage.removeItem("numen_refresh_token");
  localStorage.removeItem("numen_org_id");
  localStorage.removeItem("numen_org_name");
  localStorage.removeItem("numen_email");
  localStorage.removeItem("numen_is_demo");
  localStorage.removeItem("numen_is_admin");
  localStorage.removeItem("numen_needs_onboarding");
  localStorage.removeItem("numen_orgs");
  setAccessToken("");
  window.location.href = "/login";
}

// ── Onboarding ──

export async function completeOnboarding(data: {
  display_name: string;
  role: string;
  org_name: string;
  org_slug: string;
}): Promise<{ id: string; name: string; slug: string }> {
  return fetchApi<{ id: string; name: string; slug: string }>("/api/onboarding", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Organizations ──

export async function listOrgs(): Promise<Organization[]> {
  const res = await fetchApi<{ items: Organization[] }>("/api/orgs");
  return res.items;
}

export async function listMembers(orgId?: string): Promise<OrgMember[]> {
  const path = orgId ? `/api/orgs/${orgId}/members` : orgPath("/members");
  const res = await fetchApi<{ items: OrgMember[] }>(path);
  return res.items;
}

export async function getMember(memberId: string): Promise<OrgMember> {
  return fetchApi<OrgMember>(orgPath(`/members/${memberId}`));
}

export async function updateMember(
  memberId: string,
  data: {
    role?: string;
    display_name?: string;
    timezone?: string;
    briefing_hour?: number;
    briefing_channel?: "email" | "slack";
  },
): Promise<OrgMember> {
  return fetchApi<OrgMember>(orgPath(`/members/${memberId}`), {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function getMemberByPersonEntityId(personEntityId: string): Promise<OrgMember | null> {
  const members = await listMembers();
  return members.find((m) => m.person_entity_id === personEntityId) ?? null;
}

export async function createOrg(name: string, slug: string) {
  return fetchApi<{ id: string }>("/api/orgs", {
    method: "POST",
    body: JSON.stringify({ name, slug }),
  });
}

export async function getOrg(orgId: string) {
  return fetchApi<{ id: string; name: string; slug: string }>(`/api/orgs/${orgId}`);
}

// ── Entities (generic) ──

export async function getEntities(params?: {
  type?: string;
  source?: string;
  search?: string;
  page?: number;
  page_size?: number;
}): Promise<EntityListResponse> {
  const query = new URLSearchParams();
  if (params?.type) query.set("type", params.type);
  if (params?.source) query.set("source", params.source);
  if (params?.search) query.set("search", params.search);
  if (params?.page) query.set("page", String(params.page));
  if (params?.page_size) query.set("page_size", String(params.page_size));
  const qs = query.toString();
  return fetchApi<EntityListResponse>(orgPath(`/entities${qs ? `?${qs}` : ""}`));
}

export async function getEntity(entityId: string): Promise<EntityDetailResponse> {
  return fetchApi<EntityDetailResponse>(orgPath(`/entities/${entityId}`));
}

// ── Goals ──

export async function getGoals(): Promise<GoalResponse[]> {
  const res = await fetchApi<{ items: GoalResponse[] }>(orgPath("/goals"));
  return res.items;
}

export async function getGoalTree(): Promise<GoalTreeNode[]> {
  const res = await fetchApi<{ items: GoalTreeNode[] }>(orgPath("/goals/tree"));
  return res.items;
}

export async function getGoal(goalId: string): Promise<GoalResponse> {
  return fetchApi<GoalResponse>(orgPath(`/goals/${goalId}`));
}

export async function createGoal(data: CreateGoalPayload): Promise<GoalResponse> {
  return fetchApi<GoalResponse>(orgPath("/goals"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateGoal(goalId: string, data: UpdateGoalPayload): Promise<GoalResponse> {
  return fetchApi<GoalResponse>(orgPath(`/goals/${goalId}`), {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteGoal(goalId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/goals/${goalId}`), { method: "DELETE" });
}

export async function linkEntityToGoal(
  goalId: string,
  entityId: string,
  edgeType: string,
): Promise<void> {
  await fetchApi<void>(orgPath(`/goals/${goalId}/links`), {
    method: "POST",
    body: JSON.stringify({ entity_id: entityId, edge_type: edgeType }),
  });
}

// ── Projects ──

export async function getProjects(): Promise<ProjectResponse[]> {
  const res = await fetchApi<{ items: ProjectResponse[] }>(orgPath("/projects"));
  return res.items;
}

export async function getProject(projectId: string): Promise<ProjectResponse> {
  return fetchApi<ProjectResponse>(orgPath(`/projects/${projectId}`));
}

export async function createProject(data: {
  name: string;
  description?: string;
  status?: string;
  owner_email?: string;
  start_date?: string;
  end_date?: string;
  goal_ids?: string[];
}): Promise<ProjectResponse> {
  return fetchApi<ProjectResponse>(orgPath("/projects"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateProject(projectId: string, data: Record<string, unknown>): Promise<ProjectResponse> {
  return fetchApi<ProjectResponse>(orgPath(`/projects/${projectId}`), {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteProject(projectId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/projects/${projectId}`), { method: "DELETE" });
}

export async function getProjectTasks(projectId: string): Promise<TaskResponse[]> {
  const res = await fetchApi<{ items: TaskResponse[] }>(orgPath(`/projects/${projectId}/tasks`));
  return res.items;
}

// ── Tasks ──

export async function getTasks(params?: {
  status?: string;
  priority?: string;
  assignee?: string;
  project_id?: string;
  goal_id?: string;
}): Promise<TaskResponse[]> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.priority) query.set("priority", params.priority);
  if (params?.assignee) query.set("assignee_email", params.assignee);
  if (params?.project_id) query.set("project_id", params.project_id);
  if (params?.goal_id) query.set("goal_id", params.goal_id);
  const qs = query.toString();
  const res = await fetchApi<{ items: TaskResponse[] }>(orgPath(`/tasks${qs ? `?${qs}` : ""}`));
  return res.items;
}

export async function getTask(taskId: string): Promise<TaskResponse> {
  return fetchApi<TaskResponse>(orgPath(`/tasks/${taskId}`));
}

export async function createTask(data: {
  title: string;
  description?: string;
  status?: string;
  priority?: string;
  assignee_email?: string;
  due_date?: string;
  project_id?: string;
  goal_ids?: string[];
  labels?: string[];
}): Promise<TaskResponse> {
  return fetchApi<TaskResponse>(orgPath("/tasks"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateTask(taskId: string, data: Record<string, unknown>): Promise<TaskResponse> {
  return fetchApi<TaskResponse>(orgPath(`/tasks/${taskId}`), {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteTask(taskId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/tasks/${taskId}`), { method: "DELETE" });
}

// ── Edges ──

export async function createEdge(data: {
  from_entity_id: string;
  to_entity_id: string;
  type: string;
  weight?: number;
  skip_auto_transition?: boolean;
}): Promise<Edge> {
  return fetchApi<Edge>(orgPath("/edges"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteEdge(data: {
  from_entity_id: string;
  to_entity_id: string;
  type: string;
}): Promise<void> {
  await fetchApi<void>(orgPath("/edges"), {
    method: "DELETE",
    body: JSON.stringify(data),
  });
}

export async function getEntityEdges(entityId: string, direction?: "outgoing" | "incoming"): Promise<Edge[]> {
  const params = direction ? `?direction=${direction}` : "";
  return fetchApi<Edge[]>(orgPath(`/edges/entity/${entityId}${params}`));
}

// ── Briefings ──

export async function getLatestBriefing(): Promise<Briefing> {
  return fetchApi<Briefing>(orgPath("/briefings/latest"));
}

export async function getBriefings(): Promise<Briefing[]> {
  return fetchApi<{ items: Briefing[] }>(orgPath("/briefings")).then(r => r.items);
}

export async function sendTestBriefing(): Promise<TestBriefingResponse> {
  return fetchApi<TestBriefingResponse>(orgPath("/briefings/test"), { method: "POST" });
}

export async function triggerBriefing(): Promise<Briefing> {
  return fetchApi<Briefing>(orgPath("/briefings/generate"), { method: "POST" });
}

// ── Urgency ──

export async function getUrgency(limit?: number): Promise<UrgencyScore[]> {
  const params = limit ? `?limit=${limit}` : "";
  return fetchApi<{ items: UrgencyScore[] }>(orgPath(`/urgency${params}`)).then(r => r.items);
}

// ── Connectors ──

export async function getConnectorStatus(): Promise<ConnectorStatus[]> {
  const res = await fetchApi<{ items: ConnectorStatus[] }>(orgPath("/connectors"));
  return res.items;
}

export async function getConnectorAuthUrl(connector: string): Promise<string> {
  const res = await fetchApi<{ redirect_url: string }>(
    `/auth/${connector}/connect?org_id=${_orgId}`,
  );
  return res.redirect_url || "";
}

export async function disconnectConnector(connector: string): Promise<void> {
  await fetchApi<void>(`/auth/${connector}/disconnect?org_id=${_orgId}`, {
    method: "DELETE",
  });
}

export async function exchangeConnectorCode(
  connector: string,
  code: string,
  state: string,
): Promise<void> {
  const params = new URLSearchParams({ code, state });
  await fetchApi<{ status: string }>(`/auth/${connector}/callback?${params.toString()}`);
}

export async function getGitHubRepos(): Promise<import("@/types").GitHubRepoListResponse> {
  return fetchApi<import("@/types").GitHubRepoListResponse>(orgPath("/connectors/github/repos"));
}

export async function updateConnectorSettings(
  connector: string,
  settings: { selected_repos: string[] },
): Promise<{ selected_repos: string[]; webhook_ids: Record<string, number> }> {
  return fetchApi(orgPath(`/connectors/${connector}/settings`), {
    method: "PUT",
    body: JSON.stringify(settings),
  });
}

export async function triggerSync(
  connector: string,
): Promise<import("@/types").SyncTriggerResponse> {
  return fetchApi<import("@/types").SyncTriggerResponse>(orgPath(`/connectors/${connector}/sync`), {
    method: "POST",
  });
}

// ── Graph ──

export async function getGraphNeighborhood(entityId: string, depth?: number): Promise<GraphNeighborhoodResponse> {
  const params = depth ? `?depth=${depth}` : "";
  return fetchApi<GraphNeighborhoodResponse>(orgPath(`/graph/${entityId}${params}`));
}

export async function getFullGraph(params?: {
  entity_types?: string[];
  edge_types?: string[];
  limit?: number;
  offset?: number;
  search?: string;
}): Promise<import("@/types").FullGraphResponse> {
  const searchParams = new URLSearchParams();
  if (params?.entity_types?.length) searchParams.set("entity_types", params.entity_types.join(","));
  if (params?.edge_types?.length) searchParams.set("edge_types", params.edge_types.join(","));
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));
  if (params?.search) searchParams.set("search", params.search);
  const qs = searchParams.toString();
  return fetchApi<import("@/types").FullGraphResponse>(orgPath(`/graph${qs ? `?${qs}` : ""}`));
}

// ── Activity ──

export async function getActivity(limit?: number): Promise<import("@/types").ActivityEntry[]> {
  const params = limit ? `?limit=${limit}` : "";
  const res = await fetchApi<{ items: import("@/types").ActivityEntry[] }>(orgPath(`/activity${params}`));
  return res.items;
}

// ── Dashboard ──

export async function getDashboardSummary(): Promise<import("@/types").DashboardSummary> {
  return fetchApi<import("@/types").DashboardSummary>(orgPath("/dashboard/summary"));
}

// ── Claude dispatch ──

export async function claudeDispatch(action: string, entityId: string) {
  return fetchApi<{ action: string; entity_id: string; result: Record<string, unknown>; draft: boolean }>(
    orgPath("/dispatch"),
    { method: "POST", body: JSON.stringify({ action, entity_id: entityId }) },
  );
}

// ── AI Prompt Generation ──

export async function generateTaskPrompt(taskId: string): Promise<import("@/types").AiPromptResponse> {
  return fetchApi<import("@/types").AiPromptResponse>(
    orgPath(`/tasks/${taskId}/ai-prompt`),
    { method: "POST" },
  );
}

// ── People / Org Graph ──

export interface OrgGraphResponse {
  people: import("@/types").Entity[];
  edges: import("@/types").Edge[];
}

export async function getOrgGraph(): Promise<OrgGraphResponse> {
  return fetchApi<OrgGraphResponse>(orgPath("/people/graph"));
}

export async function createPerson(data: {
  name: string;
  email?: string;
  role?: string;
  title?: string;
  manager_id?: string;
}): Promise<import("@/types").Entity> {
  return fetchApi<import("@/types").Entity>(orgPath("/people"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Link Suggestions ──

export async function getLinkSuggestions(status?: string, limit?: number): Promise<import("@/types").LinkSuggestion[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (limit) params.set("limit", String(limit));
  const qs = params.toString();
  const res = await fetchApi<{ items: import("@/types").LinkSuggestion[] }>(orgPath(`/suggestions${qs ? `?${qs}` : ""}`));
  return res.items;
}

export async function getLinkSuggestionCount(): Promise<{ pending: number }> {
  return fetchApi<{ pending: number }>(orgPath("/suggestions/count"));
}

export async function acceptSuggestion(
  suggestionId: string,
  skipAutoTransition?: boolean,
): Promise<import("@/types").LinkSuggestion> {
  const params = skipAutoTransition ? "?skip_auto_transition=true" : "";
  return fetchApi<import("@/types").LinkSuggestion>(orgPath(`/suggestions/${suggestionId}/accept${params}`), {
    method: "POST",
  });
}

export async function dismissSuggestion(suggestionId: string): Promise<import("@/types").LinkSuggestion> {
  return fetchApi<import("@/types").LinkSuggestion>(orgPath(`/suggestions/${suggestionId}/dismiss`), {
    method: "POST",
  });
}

// ── Task Transition Preview ──

export interface TransitionPreview {
  should_transition: boolean;
  current_status: string;
  target_status: string;
  pr_name: string;
  task_name: string;
}

export async function previewPrTransition(
  taskId: string,
  prEntityId: string,
): Promise<TransitionPreview | null> {
  return fetchApi<TransitionPreview | null>(
    orgPath(`/tasks/${taskId}/pr-transition-preview?pr_entity_id=${prEntityId}`),
  );
}

export async function generateSuggestions(): Promise<import("@/types").LinkSuggestion[]> {
  const res = await fetchApi<{ items: import("@/types").LinkSuggestion[] }>(orgPath("/suggestions/generate"), {
    method: "POST",
  });
  return res.items;
}

// ── Person Resolutions ──

export async function getPersonResolutions(status?: string): Promise<import("@/types").PersonResolution[]> {
  const params = status ? `?status=${status}` : "";
  const res = await fetchApi<{ items: import("@/types").PersonResolution[] }>(orgPath(`/people/resolutions${params}`));
  return res.items;
}

export async function getPersonResolutionCount(): Promise<{ pending: number }> {
  return fetchApi<{ pending: number }>(orgPath("/people/resolutions/count"));
}

export async function mergeResolution(resolutionId: string): Promise<import("@/types").PersonResolution> {
  return fetchApi<import("@/types").PersonResolution>(orgPath(`/people/resolutions/${resolutionId}/merge`), {
    method: "POST",
  });
}

export async function markResolutionDistinct(resolutionId: string): Promise<import("@/types").PersonResolution> {
  return fetchApi<import("@/types").PersonResolution>(orgPath(`/people/resolutions/${resolutionId}/distinct`), {
    method: "POST",
  });
}

export async function dismissResolution(resolutionId: string): Promise<import("@/types").PersonResolution> {
  return fetchApi<import("@/types").PersonResolution>(orgPath(`/people/resolutions/${resolutionId}/dismiss`), {
    method: "POST",
  });
}

export async function linkResolution(resolutionId: string, targetEntityId: string): Promise<import("@/types").PersonResolution> {
  return fetchApi<import("@/types").PersonResolution>(orgPath(`/people/resolutions/${resolutionId}/link`), {
    method: "POST",
    body: JSON.stringify({ target_entity_id: targetEntityId }),
  });
}

// ── PRDs ──

export async function createPrd(payload: CreatePrdPayload): Promise<PrdResponse> {
  return fetchApi<PrdResponse>(orgPath("/prds"), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getPrds(params?: {
  status?: string;
  owner?: string;
  search?: string;
  node_type?: string;
}): Promise<{ items: PrdResponse[] }> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.owner) query.set("owner", params.owner);
  if (params?.search) query.set("search", params.search);
  if (params?.node_type) query.set("node_type", params.node_type);
  const qs = query.toString();
  return fetchApi<{ items: PrdResponse[] }>(orgPath(`/prds${qs ? `?${qs}` : ""}`));
}

export async function getPrd(prdId: string): Promise<PrdResponse> {
  return fetchApi<PrdResponse>(orgPath(`/prds/${prdId}`));
}

export async function updatePrd(prdId: string, payload: UpdatePrdPayload): Promise<PrdResponse> {
  return fetchApi<PrdResponse>(orgPath(`/prds/${prdId}`), {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deletePrd(prdId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/prds/${prdId}`), { method: "DELETE" });
}

// PRD Tree

export async function getPrdTree(): Promise<{ items: PrdTreeNode[] }> {
  return fetchApi<{ items: PrdTreeNode[] }>(orgPath("/prds/tree"));
}

export async function movePrd(prdId: string, parentId: string | null, position: number): Promise<void> {
  await fetchApi<void>(orgPath(`/prds/${prdId}/move`), {
    method: "POST",
    body: JSON.stringify({ parent_id: parentId, position }),
  });
}

// PRD Blocks

export async function getPrdBlocks(prdId: string): Promise<{ items: PrdBlockResponse[] }> {
  return fetchApi<{ items: PrdBlockResponse[] }>(orgPath(`/prds/${prdId}/blocks`));
}

export async function savePrdBlocks(
  prdId: string,
  operations: PrdBlockOperation[],
): Promise<{ items: PrdBlockResponse[] }> {
  return fetchApi<{ items: PrdBlockResponse[] }>(orgPath(`/prds/${prdId}/blocks/batch`), {
    method: "PATCH",
    body: JSON.stringify({ operations }),
  });
}

// PRD Versions

export async function getPrdVersions(prdId: string): Promise<{ items: PrdVersionResponse[] }> {
  return fetchApi<{ items: PrdVersionResponse[] }>(orgPath(`/prds/${prdId}/versions`));
}

export async function getPrdVersion(prdId: string, version: number): Promise<PrdVersionResponse> {
  return fetchApi<PrdVersionResponse>(orgPath(`/prds/${prdId}/versions/${version}`));
}

export async function createPrdVersion(prdId: string, message?: string): Promise<PrdVersionResponse> {
  return fetchApi<PrdVersionResponse>(orgPath(`/prds/${prdId}/versions`), {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

// PRD Media

export async function getUploadUrl(
  prdId: string,
  fileName: string,
  fileType: string,
): Promise<{ upload_url: string; storage_key: string }> {
  return fetchApi<{ upload_url: string; storage_key: string }>(
    orgPath(`/prds/${prdId}/media/upload-url`),
    {
      method: "POST",
      body: JSON.stringify({ file_name: fileName, file_type: fileType }),
    },
  );
}

export async function confirmUpload(
  prdId: string,
  storageKey: string,
  fileName: string,
  fileType: string,
  fileSize: number,
): Promise<PrdMediaResponse> {
  return fetchApi<PrdMediaResponse>(orgPath(`/prds/${prdId}/media/confirm`), {
    method: "POST",
    body: JSON.stringify({
      storage_key: storageKey,
      file_name: fileName,
      file_type: fileType,
      file_size: fileSize,
    }),
  });
}

// PRD Graph

export async function getPrdReferences(prdId: string): Promise<{ items: PrdReference[] }> {
  return fetchApi<{ items: PrdReference[] }>(orgPath(`/prds/${prdId}/references`));
}

export async function getPrdCoverage(prdId: string): Promise<PrdCoverage> {
  return fetchApi<PrdCoverage>(orgPath(`/prds/${prdId}/coverage`));
}

// PRD Comments

export async function createComment(
  prdId: string,
  payload: { content: string; block_id?: string | null; parent_id?: string | null },
): Promise<import("@/types").PrdCommentResponse> {
  return fetchApi<import("@/types").PrdCommentResponse>(orgPath(`/prds/${prdId}/comments`), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getComments(
  prdId: string,
  params?: { block_id?: string; resolved?: boolean },
): Promise<{ items: import("@/types").PrdCommentResponse[] }> {
  const query = new URLSearchParams();
  if (params?.block_id) query.set("block_id", params.block_id);
  if (params?.resolved !== undefined) query.set("resolved", String(params.resolved));
  const qs = query.toString();
  return fetchApi<{ items: import("@/types").PrdCommentResponse[] }>(
    orgPath(`/prds/${prdId}/comments${qs ? `?${qs}` : ""}`),
  );
}

export async function updateComment(
  prdId: string,
  commentId: string,
  payload: { content: string },
): Promise<import("@/types").PrdCommentResponse> {
  return fetchApi<import("@/types").PrdCommentResponse>(orgPath(`/prds/${prdId}/comments/${commentId}`), {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deletePrdComment(prdId: string, commentId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/prds/${prdId}/comments/${commentId}`), { method: "DELETE" });
}

export async function resolveComment(prdId: string, commentId: string): Promise<import("@/types").PrdCommentResponse> {
  return fetchApi<import("@/types").PrdCommentResponse>(orgPath(`/prds/${prdId}/comments/${commentId}/resolve`), {
    method: "POST",
  });
}

export async function unresolveComment(prdId: string, commentId: string): Promise<import("@/types").PrdCommentResponse> {
  return fetchApi<import("@/types").PrdCommentResponse>(orgPath(`/prds/${prdId}/comments/${commentId}/unresolve`), {
    method: "POST",
  });
}

// PRD Reactions

export async function toggleReaction(
  prdId: string,
  blockId: string,
  emoji: string,
): Promise<{ added: boolean; reactions: import("@/types").PrdReactionResponse[] }> {
  return fetchApi<{ added: boolean; reactions: import("@/types").PrdReactionResponse[] }>(
    orgPath(`/prds/${prdId}/blocks/${blockId}/reactions`),
    {
      method: "POST",
      body: JSON.stringify({ emoji }),
    },
  );
}

export async function getBlockReactions(
  prdId: string,
  blockId: string,
): Promise<{ items: import("@/types").PrdReactionResponse[] }> {
  return fetchApi<{ items: import("@/types").PrdReactionResponse[] }>(
    orgPath(`/prds/${prdId}/blocks/${blockId}/reactions`),
  );
}

// PRD Status Transition

export async function transitionPrdStatus(prdId: string, newStatus: string): Promise<PrdResponse> {
  return fetchApi<PrdResponse>(orgPath(`/prds/${prdId}/transition`), {
    method: "POST",
    body: JSON.stringify({ new_status: newStatus }),
  });
}

// PRD Reviewers

export async function addReviewer(prdId: string, memberId: string): Promise<PrdStakeholderResponse> {
  return fetchApi<PrdStakeholderResponse>(orgPath(`/prds/${prdId}/reviewers`), {
    method: "POST",
    body: JSON.stringify({ member_id: memberId }),
  });
}

export async function removeReviewer(prdId: string, memberId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/prds/${prdId}/reviewers/${memberId}`), { method: "DELETE" });
}

// PRD Stakeholders

export async function addStakeholder(prdId: string, memberId: string): Promise<PrdStakeholderResponse> {
  return fetchApi<PrdStakeholderResponse>(orgPath(`/prds/${prdId}/stakeholders`), {
    method: "POST",
    body: JSON.stringify({ member_id: memberId }),
  });
}

export async function removeStakeholder(prdId: string, memberId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/prds/${prdId}/stakeholders/${memberId}`), { method: "DELETE" });
}

export async function getStakeholders(prdId: string): Promise<{ items: PrdStakeholderResponse[] }> {
  return fetchApi<{ items: PrdStakeholderResponse[] }>(orgPath(`/prds/${prdId}/stakeholders`));
}

// PRD Reviews

export async function submitReview(
  prdId: string,
  payload: { status: PrdReviewStatus; comment?: string | null },
): Promise<PrdReviewResponse> {
  return fetchApi<PrdReviewResponse>(orgPath(`/prds/${prdId}/reviews`), {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function getReviews(prdId: string): Promise<{ items: PrdReviewResponse[] }> {
  return fetchApi<{ items: PrdReviewResponse[] }>(orgPath(`/prds/${prdId}/reviews`));
}

export async function getReviewSummary(prdId: string): Promise<PrdReviewSummary> {
  return fetchApi<PrdReviewSummary>(orgPath(`/prds/${prdId}/reviews/summary`));
}

// PRD Export

export type ExportFormat = "markdown" | "html" | "pdf" | "notion" | "confluence" | "google_docs";

const FILE_EXPORT_FORMATS: ExportFormat[] = ["markdown", "html", "pdf"];

export async function exportPrd(
  prdId: string,
  format: ExportFormat,
  options?: Record<string, unknown>,
): Promise<Blob | { url: string; external_id: string }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  if (_accessToken) {
    headers["Authorization"] = `Bearer ${_accessToken}`;
  } else if (_memberEmail) {
    headers["X-Member-Email"] = _memberEmail;
  }

  const response = await fetch(
    `${API_BASE}${orgPath(`/prds/${prdId}/export`)}`,
    {
      method: "POST",
      headers,
      body: JSON.stringify({ format, options }),
    },
  );

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail || `Export error: ${response.status}`);
  }

  // File formats return binary content
  if (FILE_EXPORT_FORMATS.includes(format)) {
    return response.blob();
  }

  // API formats return JSON
  return response.json() as Promise<{ url: string; external_id: string }>;
}

// PRD Import

export type ImportSource = "notion" | "confluence" | "google_docs";

export async function importPrd(
  source: ImportSource,
  sourceId: string,
  parentFolderId?: string,
  baseUrl?: string,
): Promise<PrdResponse> {
  return fetchApi<PrdResponse>(orgPath("/prds/import"), {
    method: "POST",
    body: JSON.stringify({
      source,
      source_id: sourceId,
      parent_folder_id: parentFolderId ?? null,
      base_url: baseUrl ?? null,
    }),
  });
}

export async function importPrdFile(
  file: File,
  parentFolderId?: string,
): Promise<PrdResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const headers: Record<string, string> = {};
  if (_accessToken) {
    headers["Authorization"] = `Bearer ${_accessToken}`;
  } else if (_memberEmail) {
    headers["X-Member-Email"] = _memberEmail;
  }

  const params = new URLSearchParams();
  if (parentFolderId) {
    params.set("parent_folder_id", parentFolderId);
  }
  const qs = params.toString();

  const response = await fetch(
    `${API_BASE}${orgPath(`/prds/import/file${qs ? `?${qs}` : ""}`)}`,
    {
      method: "POST",
      headers,
      body: formData,
    },
  );

  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new ApiError(response.status, body.detail || `Import error: ${response.status}`);
  }

  return response.json() as Promise<PrdResponse>;
}

export async function importPrdBulk(
  source: ImportSource,
  rootPageId: string,
  parentFolderId?: string,
  baseUrl?: string,
): Promise<{ job_id: string; status: string }> {
  return fetchApi<{ job_id: string; status: string }>(orgPath("/prds/import/bulk"), {
    method: "POST",
    body: JSON.stringify({
      source,
      root_page_id: rootPageId,
      parent_folder_id: parentFolderId ?? null,
      base_url: baseUrl ?? null,
    }),
  });
}

// ── Manual People Merge ──

// ── API Keys (MCP) ──

export interface ApiKeyCreateResponse {
  id: string;
  name: string;
  key: string;
  created_at: string;
}

export interface ApiKeyItem {
  id: string;
  name: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

export async function createApiKey(name: string): Promise<ApiKeyCreateResponse> {
  return fetchApi<ApiKeyCreateResponse>(orgPath("/api-keys"), {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function listApiKeys(): Promise<ApiKeyItem[]> {
  const res = await fetchApi<{ items: ApiKeyItem[] }>(orgPath("/api-keys"));
  return res.items;
}

export async function revokeApiKey(keyId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/api-keys/${keyId}`), { method: "DELETE" });
}

// ── Manual People Merge ──

export async function mergePeople(primaryId: string, duplicateId: string): Promise<import("@/types").Entity> {
  return fetchApi<import("@/types").Entity>(
    orgPath(`/people/merge?primary_id=${primaryId}&duplicate_id=${duplicateId}`),
    { method: "POST" },
  );
}

// ── PRD AI ──

export async function aiCompletePrd(
  prdId: string,
  prompt: string,
): Promise<{ items: import("@/types").AiCompletedBlock[] }> {
  return fetchApi<{ items: import("@/types").AiCompletedBlock[] }>(
    orgPath(`/prds/${prdId}/ai/complete`),
    {
      method: "POST",
      body: JSON.stringify({ prompt }),
    },
  );
}

export async function aiEditSection(
  prdId: string,
  blockIds: string[],
  instruction: string,
): Promise<{ items: import("@/types").AiCompletedBlock[] }> {
  return fetchApi<{ items: import("@/types").AiCompletedBlock[] }>(
    orgPath(`/prds/${prdId}/ai/edit-section`),
    {
      method: "POST",
      body: JSON.stringify({ block_ids: blockIds, instruction }),
    },
  );
}

export async function aiSuggestReviewers(
  prdId: string,
): Promise<{ items: import("@/types").AiSuggestedReviewer[] }> {
  return fetchApi<{ items: import("@/types").AiSuggestedReviewer[] }>(
    orgPath(`/prds/${prdId}/ai/suggest-reviewers`),
  );
}

// ── PRD Alignment ──

export async function getAlignmentChecks(
  prdId: string,
): Promise<{ items: AlignmentCheckResponse[] }> {
  return fetchApi<{ items: AlignmentCheckResponse[] }>(
    orgPath(`/prds/${prdId}/alignment`),
  );
}

export async function acknowledgeFinding(checkId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/prds/alignment/${checkId}/acknowledge`), {
    method: "POST",
  });
}

export async function resolveFinding(checkId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/prds/alignment/${checkId}/resolve`), {
    method: "POST",
  });
}

// ── Wiki (feature-centric) ──

export async function getWikiLanding(): Promise<import("@/types").WikiLandingResponse> {
  return fetchApi<import("@/types").WikiLandingResponse>(orgPath("/wiki"));
}

export async function getWikiFeature(slug: string): Promise<import("@/types").WikiFeatureDetail> {
  return fetchApi<import("@/types").WikiFeatureDetail>(orgPath(`/wiki/features/${slug}`));
}

export async function updateWikiFeature(
  slug: string,
  data: import("@/types").WikiFeatureUpdateRequest,
): Promise<import("@/types").WikiFeatureDetail> {
  return fetchApi<import("@/types").WikiFeatureDetail>(orgPath(`/wiki/features/${slug}`), {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function getWikiConcept(slug: string): Promise<import("@/types").WikiConceptDetail> {
  return fetchApi<import("@/types").WikiConceptDetail>(orgPath(`/wiki/concepts/${slug}`));
}

export async function generateWiki(): Promise<import("@/types").WikiGenerateResponse> {
  return fetchApi<import("@/types").WikiGenerateResponse>(orgPath("/wiki/generate"), {
    method: "POST",
  });
}

export async function getWikiGraph(): Promise<import("@/types").WikiGraphResponse> {
  return fetchApi<import("@/types").WikiGraphResponse>(orgPath("/wiki/graph"));
}

// ── Chat ──

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface EntityReference {
  id: string;
  name: string;
  type: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_calls?: { tool: string; input: Record<string, unknown> }[] | null;
  referenced_entities?: EntityReference[] | null;
  created_at: string;
}

export async function createConversation(): Promise<Conversation> {
  return fetchApi<Conversation>(orgPath("/chat/conversations"), { method: "POST" });
}

export async function getConversations(): Promise<Conversation[]> {
  const res = await fetchApi<{ items: Conversation[] }>(orgPath("/chat/conversations"));
  return res.items;
}

export async function getChatMessages(conversationId: string): Promise<ChatMessage[]> {
  const res = await fetchApi<{ items: ChatMessage[] }>(orgPath(`/chat/conversations/${conversationId}/messages`));
  return res.items;
}

export async function deleteChatConversation(conversationId: string): Promise<void> {
  await fetchApi<void>(orgPath(`/chat/conversations/${conversationId}`), { method: "DELETE" });
}

export function sendChatMessage(
  conversationId: string,
  content: string,
  onToken: (token: string) => void,
  onToolStart?: (tool: string) => void,
  onToolEnd?: (tool: string) => void,
  onDone?: () => void,
  onError?: (error: string) => void,
  onEntities?: (entities: EntityReference[]) => void,
  /** Replaces everything streamed so far, when the reply had to be redacted. */
  onSanitized?: (content: string) => void,
): AbortController {
  const controller = new AbortController();
  const url = `${API_BASE}${orgPath(`/chat/conversations/${conversationId}/messages`)}`;

  fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(_accessToken
        ? { "Authorization": `Bearer ${_accessToken}` }
        : _memberEmail
          ? { "X-Member-Email": _memberEmail }
          : {}),
    },
    body: JSON.stringify({ content }),
    signal: controller.signal,
  }).then(async (response) => {
    if (!response.ok) {
      onError?.(`API error: ${response.status}`);
      return;
    }
    const reader = response.body?.getReader();
    if (!reader) return;

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === "token") onToken(data.content);
          else if (data.type === "tool_start") onToolStart?.(data.tool);
          else if (data.type === "tool_end") onToolEnd?.(data.tool);
          else if (data.type === "entities") onEntities?.(data.entities);
          else if (data.type === "sanitized") onSanitized?.(data.content);
          else if (data.type === "done") onDone?.();
          else if (data.type === "error") onError?.(data.content);
        } catch {
          // ignore parse errors
        }
      }
    }
  }).catch((err) => {
    if (err.name !== "AbortError") {
      onError?.(err.message);
    }
  });

  return controller;
}

// ── Task Activity / Comments ──

export async function getTaskActivity(taskId: string) {
  return fetchApi<{ items: TaskActivity[] }>(orgPath(`/tasks/${taskId}/activity`));
}

export async function addComment(taskId: string, content: string) {
  return fetchApi<TaskActivity>(orgPath(`/tasks/${taskId}/comments`), {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export async function editComment(taskId: string, commentId: string, content: string) {
  return fetchApi<TaskActivity>(orgPath(`/tasks/${taskId}/comments/${commentId}`), {
    method: "PUT",
    body: JSON.stringify({ content }),
  });
}

export async function deleteComment(taskId: string, commentId: string) {
  return fetchApi<void>(orgPath(`/tasks/${taskId}/comments/${commentId}`), { method: "DELETE" });
}

// ── Subtasks ──

export async function getSubtasks(taskId: string) {
  return fetchApi<{ items: TaskResponse[] }>(orgPath(`/tasks/${taskId}/subtasks`));
}

export async function createSubtask(taskId: string, data: { title: string; description?: string; priority?: string; assignee_email?: string; due_date?: string; labels?: string[] }) {
  return fetchApi<TaskResponse>(orgPath(`/tasks/${taskId}/subtasks`), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

// ── Saved Views ──

export async function getSavedViews() {
  return fetchApi<{ items: SavedView[] }>(orgPath("/views"));
}

export async function createSavedView(data: Partial<SavedView>) {
  return fetchApi<SavedView>(orgPath("/views"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateSavedView(viewId: string, data: Partial<SavedView>) {
  return fetchApi<SavedView>(orgPath(`/views/${viewId}`), {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteSavedView(viewId: string) {
  return fetchApi<void>(orgPath(`/views/${viewId}`), { method: "DELETE" });
}

// ── Kanban Settings ──

export async function getKanbanSettings() {
  return fetchApi<KanbanSettings>(orgPath("/kanban/settings"));
}

export async function updateKanbanSettings(items: KanbanSettingItem[]) {
  return fetchApi<KanbanSettings>(orgPath("/kanban/settings"), {
    method: "PUT",
    body: JSON.stringify({ items }),
  });
}

// ── Sprints ──

export async function getSprints(status?: string) {
  const params = status ? `?status=${status}` : "";
  return fetchApi<{ items: Sprint[] }>(orgPath(`/sprints${params}`));
}

export async function getSprint(sprintId: string) {
  return fetchApi<Sprint>(orgPath(`/sprints/${sprintId}`));
}

export async function createSprint(data: { name: string; start_date?: string; end_date?: string; goal?: string; velocity_target?: number }) {
  return fetchApi<Sprint>(orgPath("/sprints"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateSprint(sprintId: string, data: Record<string, unknown>) {
  return fetchApi<Sprint>(orgPath(`/sprints/${sprintId}`), {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function addTasksToSprint(sprintId: string, taskIds: string[]) {
  return fetchApi<void>(orgPath(`/sprints/${sprintId}/tasks`), {
    method: "POST",
    body: JSON.stringify({ task_ids: taskIds }),
  });
}

export async function removeTaskFromSprint(sprintId: string, taskId: string) {
  return fetchApi<void>(orgPath(`/sprints/${sprintId}/tasks/${taskId}`), { method: "DELETE" });
}

// ── Task Templates ──

export async function getTemplates() {
  return fetchApi<{ items: TaskTemplate[] }>(orgPath("/templates"));
}

export async function createTemplate(data: { name: string; description?: string; default_properties?: Record<string, unknown>; subtask_titles?: string[] }) {
  return fetchApi<TaskTemplate>(orgPath("/templates"), {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function updateTemplate(templateId: string, data: Record<string, unknown>) {
  return fetchApi<TaskTemplate>(orgPath(`/templates/${templateId}`), {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

export async function deleteTemplate(templateId: string) {
  return fetchApi<void>(orgPath(`/templates/${templateId}`), { method: "DELETE" });
}

export async function applyTemplate(templateId: string) {
  return fetchApi<TaskResponse>(orgPath(`/templates/${templateId}/apply`), { method: "POST" });
}

// ── Notifications ──

export async function getNotifications() {
  return fetchApi<{ items: AppNotification[] }>(orgPath("/notifications"));
}

export async function markNotificationRead(notificationId: string) {
  return fetchApi<void>(orgPath(`/notifications/${notificationId}/read`), { method: "POST" });
}

export async function markAllNotificationsRead() {
  return fetchApi<void>(orgPath("/notifications/read-all"), { method: "POST" });
}

export async function getUnreadNotificationCount() {
  return fetchApi<{ count: number }>(orgPath("/notifications/unread-count"));
}

// ── Attachments ──

export async function getAttachments(taskId: string) {
  return fetchApi<{ items: Attachment[] }>(orgPath(`/tasks/${taskId}/attachments`));
}

export async function uploadAttachment(taskId: string, file: File) {
  const formData = new FormData();
  formData.append("file", file);
  // Use raw fetch for multipart - fetchApi adds JSON content-type
  const orgId = localStorage.getItem("numen_org_id");
  const token = localStorage.getItem("numen_access_token");
  const res = await fetch(`${API_BASE}/api/orgs/${orgId}/tasks/${taskId}/attachments`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
  if (!res.ok) throw new Error("Upload failed");
  return res.json() as Promise<Attachment>;
}

export async function deleteAttachment(taskId: string, attachmentId: string) {
  return fetchApi<void>(orgPath(`/tasks/${taskId}/attachments/${attachmentId}`), { method: "DELETE" });
}

export async function downloadAttachment(attachmentId: string) {
  const orgId = localStorage.getItem("numen_org_id");
  const token = localStorage.getItem("numen_access_token");
  const res = await fetch(`${API_BASE}/api/orgs/${orgId}/attachments/${attachmentId}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Download failed");
  return res.blob();
}
