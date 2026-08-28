// ── Enums (match backend src/shared/types.py exactly) ──

export const EntityType = {
  PERSON: "person",
  TASK: "task",
  COMMIT_PR: "commit_pr",
  DEPLOY: "deploy",
  INCIDENT: "incident",
  ERROR_EVENT: "error_event",
  METRIC_SNAPSHOT: "metric_snapshot",
  FEATURE: "feature",
  PROJECT: "project",
  GOAL: "goal",
  DOCUMENT: "document",
  DECISION: "decision",
  SPRINT: "sprint",
} as const;
export type EntityType = (typeof EntityType)[keyof typeof EntityType];

export const EdgeType = {
  OWNS: "owns",
  BLOCKS: "blocks",
  DEPENDS_ON: "depends_on",
  AUTHORED: "authored",
  MENTIONED_IN: "mentioned_in",
  SHIPS_TO: "ships_to",
  MEASURES: "measures",
  CAUSED_BY: "caused_by",
  TAGGED_TO: "tagged_to",
  CONFLICTS_WITH: "conflicts_with",
  CONTAINS: "contains",
  PARENT_OF: "parent_of",
  ASSIGNED_TO: "assigned_to",
  REPORTS_TO: "reports_to",
  MEMBER_OF: "member_of",
  SURFACED_TO: "surfaced_to",
  ACTED_ON: "acted_on",
  DISMISSED: "dismissed",
  APPROVED_BY: "approved_by",
  ESCALATED_TO: "escalated_to",
  PRECEDED_BY: "preceded_by",
  REVIEWS: "reviews",
  DEPLOYED_BY: "deployed_by",
  // PRD-specific edges
  REFERENCES: "references",
  STAKEHOLDER_OF: "stakeholder_of",
  REVIEWER_OF: "reviewer_of",
  IMPLEMENTS: "implements",
  DESIGNS_FOR: "designs_for",
  SECTION_LINKS_TO: "section_links_to",
} as const;
export type EdgeType = (typeof EdgeType)[keyof typeof EdgeType];

export const SourceType = {
  LINEAR: "linear",
  GITHUB: "github",
  SLACK: "slack",
  NOTION: "notion",
  DATADOG: "datadog",
  SENTRY: "sentry",
  PAGERDUTY: "pagerduty",
  AMPLITUDE: "amplitude",
  POSTHOG: "posthog",
  FIGMA: "figma",
  MANUAL: "manual",
} as const;
export type SourceType = (typeof SourceType)[keyof typeof SourceType];

export const RoleType = {
  ENGINEER: "engineer",
  PM: "pm",
  EM: "em",
  CTO: "cto",
  VP_ENG: "vp_eng",
  VP_PRODUCT: "vp_product",
  DESIGNER: "designer",
} as const;
export type RoleType = (typeof RoleType)[keyof typeof RoleType];

// Property value enums

export const GoalLevel = {
  COMPANY: "company",
  TEAM: "team",
  INDIVIDUAL: "individual",
} as const;
export type GoalLevel = (typeof GoalLevel)[keyof typeof GoalLevel];

export const TaskStatus = {
  BACKLOG: "backlog",
  TODO: "todo",
  IN_PROGRESS: "in_progress",
  IN_REVIEW: "in_review",
  MERGED: "merged",
  DONE: "done",
  ARCHIVED: "archived",
} as const;
export type TaskStatus = (typeof TaskStatus)[keyof typeof TaskStatus];

export const ProjectStatus = {
  PLANNING: "planning",
  ACTIVE: "active",
  PAUSED: "paused",
  COMPLETED: "completed",
  ARCHIVED: "archived",
} as const;
export type ProjectStatus =
  (typeof ProjectStatus)[keyof typeof ProjectStatus];

export const Priority = {
  URGENT: "urgent",
  HIGH: "high",
  MEDIUM: "medium",
  LOW: "low",
  NONE: "none",
} as const;
export type Priority = (typeof Priority)[keyof typeof Priority];

export const PrdStatus = {
  IDEA: "idea",
  DRAFT: "draft",
  IN_REVIEW: "in_review",
  NEEDS_REVISION: "needs_revision",
  APPROVED: "approved",
  IN_PROGRESS: "in_progress",
  SHIPPED: "shipped",
  DEPRECATED: "deprecated",
  ARCHIVED: "archived",
} as const;
export type PrdStatus = (typeof PrdStatus)[keyof typeof PrdStatus];

export const PrdNodeType = {
  FOLDER: "folder",
  DOCUMENT: "document",
  IMAGE: "image",
} as const;
export type PrdNodeType = (typeof PrdNodeType)[keyof typeof PrdNodeType];

export const PrdReviewStatus = {
  PENDING: "pending",
  APPROVED: "approved",
  CHANGES_REQUESTED: "changes_requested",
} as const;
export type PrdReviewStatus =
  (typeof PrdReviewStatus)[keyof typeof PrdReviewStatus];

// ── Core interfaces (match backend response schemas) ──

export interface Entity {
  id: string;
  org_id: string;
  type: EntityType;
  source: SourceType;
  source_ids: Record<string, string>;
  canonical_name: string;
  properties: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface Edge {
  id: string;
  from_entity_id: string;
  to_entity_id: string;
  type: EdgeType;
  weight: number;
  confidence: number;
  first_seen_at: string;
  last_active_at: string;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  is_demo?: boolean;
  created_at: string;
}

export interface OrgMember {
  id: string;
  org_id: string;
  email: string;
  display_name: string | null;
  role: RoleType;
  timezone: string;
  person_entity_id: string | null;
  created_at: string;
  briefing_hour: number;
  briefing_channel: "email" | "slack";
}

// ── Domain-specific typed properties ──

export interface KeyResult {
  title: string;
  target_value: number;
  current_value: number;
  unit: string;
}

export interface GoalProperties {
  level: GoalLevel;
  status: string;
  key_results: KeyResult[];
  target_value: number | null;
  current_value: number | null;
  owner_email: string | null;
  time_bound_start: string | null;
  time_bound_end: string | null;
  progress_mode: "manual" | "computed";
}

export interface ProjectProperties {
  status: ProjectStatus;
  description: string | null;
  owner_email: string | null;
  start_date: string | null;
  end_date: string | null;
  priority: Priority;
}

export interface TaskProperties {
  status: TaskStatus;
  priority: Priority;
  assignee_email: string | null;
  due_date: string | null;
  description: string | null;
  labels: string[];
  source_url: string | null;
  story_points: number | null;
  estimated_hours: number | null;
}

// ── API response types ──

export interface EntityListResponse {
  items: Entity[];
  total: number;
  page: number;
  page_size: number;
}

export interface EntityDetailResponse {
  entity: Entity;
  edges: Edge[];
}

export interface GoalResponse {
  id: string;
  title: string;
  level: GoalLevel;
  status: string;
  key_results: KeyResult[];
  target_value: number | null;
  current_value: number | null;
  computed_progress: number | null;
  owner: string | null;
  parent_goal_id: string | null;
  child_goal_ids: string[];
  linked_project_ids: string[];
  time_bound_start: string | null;
  time_bound_end: string | null;
  created_at: string;
  updated_at: string;
}

export interface GoalTreeNode extends GoalResponse {
  children: GoalTreeNode[];
}

export interface CreateGoalPayload {
  title: string;
  level: GoalLevel;
  key_results?: KeyResult[];
  target_value?: number | null;
  owner?: string | null;
  parent_goal_id?: string | null;
  time_bound_start?: string | null;
  time_bound_end?: string | null;
}

export interface UpdateGoalPayload extends Partial<CreateGoalPayload> {
  status?: string;
  current_value?: number | null;
}

export interface ProjectResponse {
  id: string;
  name: string;
  description: string | null;
  status: ProjectStatus;
  owner: string | null;
  start_date: string | null;
  end_date: string | null;
  task_count: number;
  tasks_done: number;
  goal_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface ProjectCreateRequest {
  name: string;
  description?: string;
  status?: string;
  owner_email?: string;
  start_date?: string;
  end_date?: string;
  goal_ids?: string[];
}

export interface ProjectUpdateRequest {
  name?: string;
  description?: string;
  status?: string;
  owner_email?: string;
  start_date?: string;
  end_date?: string;
  goal_ids?: string[];
}

export interface TaskResponse {
  id: string;
  title: string;
  status: TaskStatus;
  priority: Priority;
  assignee: string | null;
  due_date: string | null;
  description: string | null;
  source: SourceType;
  project_id: string | null;
  goal_ids: string[];
  labels: string[];
  story_points: number | null;
  estimated_hours: number | null;
  parent_id: string | null;
  subtask_count: number;
  created_at: string;
  updated_at: string;
}

export interface BriefingItem {
  entity_id: string;
  entity_type: EntityType;
  title: string;
  why_it_matters: string;
  urgency_score: number;
  goal_tags: string[];
  source_links: { source: string; label: string; url: string }[];
  suggested_action: string | null;
}

export type BriefingEmptyReason =
  | "no_person_entity"
  | "no_urgent_signals";

export interface Briefing {
  id: string;
  org_member_id: string;
  generated_at: string;
  items: BriefingItem[];
  empty_reason: BriefingEmptyReason | null;
  delivery_status: string;
  delivered_at: string | null;
}

export interface UrgencyScore {
  entity_id: string;
  entity_name: string;
  entity_type: EntityType;
  score: number;
  score_components: Record<string, unknown>;
  goal_ids: string[];
  provenance: Record<string, unknown>[];
  computed_at: string;
}

export interface ConnectorStatus {
  connector: SourceType;
  connected: boolean;
  last_sync_at: string | null;
  status: string;
  error_message: string | null;
  needs_reauth?: boolean;
}

export interface TestBriefingResponse {
  channel: "email" | "slack";
  delivered: boolean;
  fallback_reason: string | null;
  item_count: number;
  message: string;
}

export interface GitHubRepo {
  full_name: string;
  name: string;
  owner: string;
  private: boolean;
  description: string | null;
  enabled: boolean;
}

export interface GitHubRepoListResponse {
  repos: GitHubRepo[];
}

export interface SyncTriggerResponse {
  status: string;
  entities_created: number;
  entities_updated: number;
  edges_created: number;
  edges_updated: number;
  errors: string[];
}

export interface GraphNeighborhoodResponse {
  entities: Entity[];
  edges: Edge[];
}

export interface FullGraphResponse {
  entities: Entity[];
  edges: Edge[];
  total_entities: number;
  total_edges: number;
  has_more: boolean;
}

// ── Activity ──

export interface ActivityEntry {
  id: string;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  created_at: string | null;
}

// ── Person resolution ──

export interface LinkSuggestion {
  id: string;
  source_entity: Entity;
  target_entity: Entity;
  edge_type: EdgeType;
  confidence: number;
  reasoning: string | null;
  status: string;
  created_at: string;
}

// ── AI prompt generation ──

export interface AiPromptResponse {
  prompt: string;
  raw_prompt: string;
  task_title: string;
  repo_urls: string[];
  has_blocking_chain: boolean;
  goal_count: number;
  llm_trace: Record<string, unknown> | null;
}

export interface PersonResolution {
  id: string;
  candidate: Entity;
  match: Entity;
  confidence: number;
  match_reasons: { type: string; value: string }[];
  status: string;
  created_at: string;
}

// ── Dashboard summary ──

export interface TaskCounts {
  active: number;
  in_review: number;
  todo: number;
  blocked: number;
  total: number;
}

export interface TeamMemberWorkload {
  person_id: string;
  person_name: string;
  todo: number;
  in_progress: number;
  in_review: number;
  done: number;
  total: number;
}

export interface DelayedProject {
  id: string;
  name: string;
  days_overdue: number;
  remaining_tasks: number;
}

export interface GoalsSummary {
  total: number;
  on_track: number;
  at_risk: number;
  no_coverage: number;
}

export interface DashboardSummary {
  role: RoleType;
  my_tasks: TaskCounts;
  pr_reviews_pending: number;
  goals_summary: GoalsSummary | null;
  team_workload: TeamMemberWorkload[] | null;
  team_size: number;
  delayed_projects: DelayedProject[] | null;
  stalled_prs_count: number;
  cross_team_blocks: number;
  recent_incidents_count: number;
}

// ── Task Activity / Comments ──

export interface TaskActivity {
  id: string;
  entity_id: string;
  activity_type: string;
  actor_id: string | null;
  actor_name: string | null;
  content: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

// ── Saved Views ──

export interface SavedView {
  id: string;
  name: string;
  entity_type: string;
  filters: Record<string, unknown>;
  sort_config: Record<string, unknown>;
  view_mode: string;
  group_by: string | null;
  is_default: boolean;
  is_shared: boolean;
  created_at: string;
  updated_at: string;
}

// ── Kanban Settings ──

export interface KanbanSettingItem {
  column_status: string;
  wip_limit: number | null;
}

export interface KanbanSettings {
  items: KanbanSettingItem[];
}

// ── Sprints ──

export interface Sprint {
  id: string;
  name: string;
  status: string;
  start_date: string | null;
  end_date: string | null;
  goal: string | null;
  velocity_target: number | null;
  task_count: number;
  story_points_total: number;
  story_points_done: number;
  created_at: string;
  updated_at: string;
}

// ── Task Templates ──

export interface TaskTemplate {
  id: string;
  name: string;
  description: string | null;
  default_properties: Record<string, unknown>;
  subtask_titles: string[];
  created_at: string;
  updated_at: string;
}

// ── PRD types ──

export interface PrdProperties {
  prd_status: PrdStatus;
  node_type: PrdNodeType;
  description: string | null;
  owner_member_id: string | null;
  priority: Priority;
  target_date: string | null;
  tags: string[];
  cover_image_url: string | null;
}

export interface PrdResponse {
  id: string;
  title: string;
  node_type: PrdNodeType;
  status: PrdStatus;
  owner: string | null;
  owner_member_id: string | null;
  description: string | null;
  priority: Priority;
  target_date: string | null;
  tags: string[];
  cover_image_url: string | null;
  parent_id: string | null;
  block_count: number;
  comment_count: number;
  version: number;
  created_at: string;
  updated_at: string;
}

// ── Notifications ──

export interface AppNotification {
  id: string;
  type: string;
  entity_id: string | null;
  actor_id: string | null;
  actor_name: string | null;
  title: string;
  details: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

// ── Attachments ──

export interface Attachment {
  id: string;
  entity_id: string;
  filename: string;
  file_size: number | null;
  mime_type: string | null;
  created_at: string;
}

export interface PrdTreeNode {
  id: string;
  title: string;
  node_type: PrdNodeType;
  status: PrdStatus;
  parent_id: string | null;
  position: number;
  children: PrdTreeNode[];
}

export interface PrdBlockResponse {
  id: string;
  entity_id: string;
  parent_id: string | null;
  slug: string;
  block_type: string;
  content: Record<string, unknown>;
  position: number;
  heading_level: number | null;
  created_at: string;
  updated_at: string;
}

export interface PrdBlockOperation {
  op: "create" | "update" | "delete";
  id?: string;
  block_type?: string;
  content?: Record<string, unknown>;
  position?: number;
  heading_level?: number | null;
  parent_id?: string | null;
}

export interface PrdVersionResponse {
  id: string;
  entity_id: string;
  version: number;
  status_at: string;
  created_by: string;
  message: string | null;
  created_at: string;
  snapshot?: Record<string, unknown>;
}

export interface PrdCommentResponse {
  id: string;
  entity_id: string;
  block_id: string | null;
  parent_id: string | null;
  author_id: string;
  author_name: string | null;
  content: string;
  is_resolved: boolean;
  resolved_by: string | null;
  resolved_at: string | null;
  replies: PrdCommentResponse[];
  created_at: string;
  updated_at: string;
}

export interface PrdReactionResponse {
  emoji: string;
  count: number;
  member_ids: string[];
  reacted_by_me: boolean;
}

export interface PrdReviewResponse {
  id: string;
  entity_id: string;
  reviewer_id: string;
  reviewer_name: string | null;
  version: number;
  status: PrdReviewStatus;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

export interface PrdMediaResponse {
  id: string;
  entity_id: string;
  file_name: string;
  file_type: string;
  file_size: number;
  cdn_url: string;
  created_at: string;
}

export interface PrdCoverage {
  total_tasks: number;
  tasks_done: number;
  tasks_in_progress: number;
  tasks_todo: number;
  coverage_pct: number;
  linked_prs: number;
  has_design: boolean;
}

export interface PrdReference {
  prd_id: string;
  prd_title: string;
  direction: "outgoing" | "incoming";
  section_slug: string | null;
}

export interface CreatePrdPayload {
  title: string;
  node_type: PrdNodeType;
  parent_id?: string | null;
  description?: string;
  priority?: Priority;
  target_date?: string;
  tags?: string[];
  position?: number;
}

export interface UpdatePrdPayload {
  title?: string;
  status?: PrdStatus;
  description?: string;
  priority?: Priority;
  target_date?: string;
  tags?: string[];
  cover_image_url?: string;
  owner_member_id?: string;
}

export interface PrdReviewSummary {
  total_reviewers: number;
  approved_count: number;
  changes_requested_count: number;
  pending_count: number;
  can_approve: boolean;
}

export interface PrdStakeholderResponse {
  person_id: string;
  person_name: string;
  role_type: "owner" | "stakeholder" | "reviewer";
  member_id: string | null;
}

// ── PRD Alignment types ──

export type AlignmentFindingType =
  | "missing_requirement"
  | "label_mismatch"
  | "assumption_conflict"
  | "scope_drift";

export type AlignmentSeverity = "high" | "medium" | "low";

export interface AlignmentFinding {
  type: AlignmentFindingType;
  prd_section: string;
  detail: string;
  severity: AlignmentSeverity;
}

export interface AlignmentCheckResponse {
  id: string;
  prd_entity_id: string;
  prd_title: string | null;
  pr_entity_id: string;
  pr_title: string | null;
  findings: AlignmentFinding[];
  coverage_score: number | null;
  status: "pending" | "acknowledged" | "resolved";
  created_at: string;
}

// ── PRD AI types ──

export interface AiCompletedBlock {
  block_type: string;
  content: Record<string, unknown>;
  heading_level: number | null;
  position: number;
  ai_generated: boolean;
}

export interface AiSuggestedReviewer {
  member_id: string;
  person_name: string;
  reason: string;
  score: number;
}

export interface PrdAlignmentFinding {
  type: "missing_requirement" | "label_mismatch" | "assumption_conflict" | "scope_drift";
  prd_section: string;
  detail: string;
  severity: "high" | "medium" | "low";
}

export interface PrdAlignmentCheckResponse {
  id: string;
  prd_entity_id: string;
  pr_entity_id: string;
  findings: PrdAlignmentFinding[];
  coverage_score: number | null;
  status: string;
  created_at: string;
}

// ── Wiki types (feature-centric) ──

export interface WikiProductSummary {
  summary: string;
  feature_count: number;
  prd_count: number;
  generated_at: string | null;
}

export interface WikiPrdReference {
  entity_id: string;
  prd_title: string;
  section_slugs: string[];
  confidence: "extracted" | "inferred";
}

export interface WikiConceptBrief {
  id: string;
  term: string;
  slug: string;
}

export interface WikiImplementation {
  people: Array<{ id: string; name: string; role: string }>;
  tasks: Array<{ prd_entity_id: string; total: number; done: number; in_progress: number }>;
  prs: Array<{ prd_entity_id: string; count: number }>;
}

export interface WikiStats {
  total_features: number;
  active: number;
  planned: number;
  manual_edits: number;
  concept_count: number;
}

export interface WikiFeatureListItem {
  id: string;
  title: string;
  slug: string;
  description: string;
  domain_group: string;
  status: string;
  is_manual: boolean;
  prd_count: number;
}

export interface WikiLandingResponse {
  summary: WikiProductSummary;
  features: WikiFeatureListItem[];
  domain_groups: string[];
  stats: WikiStats;
}

export interface WikiFeatureDetail {
  id: string;
  title: string;
  slug: string;
  description: string;
  summary: string;
  domain_group: string;
  status: string;
  is_manual: boolean;
  prd_references: WikiPrdReference[];
  concepts: WikiConceptBrief[];
  related_features: WikiFeatureListItem[];
  implementation: WikiImplementation;
  prd_count: number;
  llm_trace: Record<string, unknown> | null;
  generated_at: string | null;
  updated_at: string | null;
}

export interface WikiConceptDetail {
  id: string;
  term: string;
  slug: string;
  definition: string;
  prd_references: WikiPrdReference[];
  features: WikiFeatureListItem[];
  generated_at: string | null;
}

export interface WikiGraphNode {
  id: string;
  type: "feature" | "prd" | "concept";
  label: string;
  status: string;
  domain_group?: string | null;
}

export interface WikiGraphEdge {
  source: string;
  target: string;
  type: string;
  label: string;
}

export interface WikiGraphResponse {
  nodes: WikiGraphNode[];
  edges: WikiGraphEdge[];
}

export interface WikiGenerateResponse {
  features: WikiFeatureListItem[];
  concepts: Array<{ id: string; term: string; slug: string; definition: string }>;
  summary: WikiProductSummary | null;
  generated: boolean;
  message: string;
  llm_trace: Record<string, unknown> | null;
}

export interface WikiFeatureUpdateRequest {
  title?: string;
  description?: string;
  domain_group?: string;
  status?: string;
}
