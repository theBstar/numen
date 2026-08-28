// Types for the Living PRD view (Lane C of the Living spike).
//
// The backend endpoints (GET /api/living/prd/:id and
// POST /api/living/prd/:id/conflicts/:conflict_id/resolve) are being built in
// Lane B. These types are the contract Lane C is building against; if Lane B
// changes the wire shape, update here and adjust call-sites accordingly.

export type LivingPrdSourceType = "notion" | "gdocs" | "git" | "slack";

export interface SourceDot {
  /** Source system the dot represents. */
  type: LivingPrdSourceType;
  /** Relative weight 0-1 - drives dot size / stack ordering. */
  weight: number;
}

export interface AgentRead {
  /** Foreign agent task id (e.g. "#task_42"). */
  taskId: string;
  /** Stable agent id (e.g. "claude-3-haiku-001"). */
  agentId: string;
  /** ISO-8601 timestamp the read happened. */
  when: string;
  /** Section ids the agent fetched chunks from in this read. */
  sectionsRead: string[];
}

export interface ConflictSourceClaim {
  /** Tag the source provides itself (e.g. "notion#abc") - displayed verbatim. */
  tag: string;
  /** Snippet of the conflicting value as the source last reported it. */
  value: string;
  /** ISO-8601 timestamp the source was last queried. */
  queriedAt: string;
}

export interface Conflict {
  /** Stable id - used in the resolve endpoint. */
  id: string;
  /** All source claims that disagree (>= 2). */
  sources: ConflictSourceClaim[];
}

export interface LivingPrdSection {
  id: string;
  title: string;
  /** Markdown body, rendered with react-markdown. */
  body: string;
  sources: SourceDot[];
  /** 0-1, surfaced as a numeric badge. */
  confidence: number;
  /** Live indicator - empty array if no agent has read this section recently. */
  recentAgentReads: AgentRead[];
  /** Present iff the section has unresolved disagreement between sources. */
  conflict?: Conflict;
}

export interface LivingPrd {
  id: string;
  title: string;
  /** Workspace name shown in the breadcrumb. */
  workspace: string;
  /** Last sync ISO-8601 timestamp - drives "last sync Xm ago" indicator. */
  lastSyncAt: string;
  /** Number of distinct agents that have read this PRD today. */
  readsToday: number;
  /** Connection state for the live-indicator dot. */
  connectionStatus: "connected" | "reconnecting" | "offline";
  sections: LivingPrdSection[];
}

export type ConflictResolutionChoice =
  | { kind: "pick_source"; sourceTag: string }
  | { kind: "manual"; value: string };

export interface ResolveConflictPayload {
  resolution: ConflictResolutionChoice;
}
