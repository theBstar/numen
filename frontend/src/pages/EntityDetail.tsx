import { useState, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  ExternalLink,
} from "lucide-react";
import { EntityType, TaskStatus, type Entity, type Edge, type EntityType as EntityTypeT } from "@/types";
import { useEntity, useGraphNeighborhood } from "@/hooks/queries";
import { EntityCard } from "@/components/EntityCard";
import { cn, formatRelativeTime, formatDate } from "@/lib/utils";

// ── TypeBadge ──

const badgeConfig: Record<EntityTypeT, { color: string; bg: string; label: string }> = {
  task: { color: "text-blue-700", bg: "bg-blue-100", label: "Task" },
  goal: { color: "text-purple-700", bg: "bg-purple-100", label: "Goal" },
  project: { color: "text-green-700", bg: "bg-green-100", label: "Project" },
  person: { color: "text-amber-700", bg: "bg-amber-100", label: "Person" },
  commit_pr: { color: "text-cyan-700", bg: "bg-cyan-100", label: "PR" },
  incident: { color: "text-red-700", bg: "bg-red-100", label: "Incident" },
  deploy: { color: "text-teal-700", bg: "bg-teal-100", label: "Deploy" },
  feature: { color: "text-teal-700", bg: "bg-teal-100", label: "Feature" },
  document: { color: "text-gray-700", bg: "bg-gray-100", label: "Document" },
  decision: { color: "text-orange-700", bg: "bg-orange-100", label: "Decision" },
  error_event: { color: "text-red-700", bg: "bg-red-100", label: "Error" },
  metric_snapshot: { color: "text-indigo-700", bg: "bg-indigo-100", label: "Metric" },
  sprint: { color: "text-violet-700", bg: "bg-violet-100", label: "Sprint" },
};

function TypeBadge({ type }: { type: EntityTypeT }) {
  const cfg = badgeConfig[type] ?? badgeConfig.task;
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold", cfg.bg, cfg.color)}>
      {cfg.label}
    </span>
  );
}

// ── EntityHeader ──

function EntityHeader({ entity }: { entity: Entity }) {
  const navigate = useNavigate();
  return (
    <div>
      <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-sm text-surface-500 hover:text-primary-600 transition-colors">
        <ArrowLeft size={14} />
        Back
      </button>
      <div className="mt-4 flex items-center gap-3">
        <TypeBadge type={entity.type} />
        <h1 className="text-2xl font-bold text-surface-900">{entity.canonical_name}</h1>
      </div>
      <div className="mt-2 flex items-center gap-4 text-sm text-surface-500">
        <span>Source: {entity.source}</span>
        <span>Created: {formatDate(entity.created_at)}</span>
        <span>Updated: {formatRelativeTime(entity.updated_at)}</span>
      </div>
    </div>
  );
}

// ── Type-Specific Sections ──

function TaskSection({ entity }: { entity: Entity }) {
  const p = entity.properties;
  const status = (p.status as string) ?? TaskStatus.TODO;
  const priority = (p.priority as string) ?? "medium";
  const assignee = (p.assignee_email as string) ?? null;
  const dueDate = (p.due_date as string) ?? null;
  const description = (p.description as string) ?? null;
  const labels = (p.labels as string[]) ?? [];

  return (
    <div className="card space-y-3">
      <h2 className="font-semibold text-surface-900">Task Details</h2>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="text-surface-500">Status:</span>{" "}
          <span className={cn("badge", status === TaskStatus.DONE ? "bg-green-100 text-green-700" : status === TaskStatus.IN_PROGRESS ? "bg-blue-100 text-blue-700" : status === TaskStatus.IN_REVIEW ? "bg-purple-100 text-purple-700" : "bg-surface-100 text-surface-600")}>
            {status.replace(/_/g, " ")}
          </span>
        </div>
        <div>
          <span className="text-surface-500">Priority:</span>{" "}
          <span className={cn("badge", priority === "urgent" ? "bg-red-100 text-red-700" : priority === "high" ? "bg-orange-100 text-orange-700" : priority === "medium" ? "bg-yellow-100 text-yellow-700" : "bg-surface-100 text-surface-600")}>
            {priority}
          </span>
        </div>
        {assignee && <div><span className="text-surface-500">Assignee:</span> {assignee}</div>}
        {dueDate && <div><span className="text-surface-500">Due:</span> {formatDate(dueDate)}</div>}
      </div>
      {labels.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {labels.map((l) => (
            <span key={l} className="badge bg-surface-100 text-surface-600">{l}</span>
          ))}
        </div>
      )}
      {description && <p className="text-sm text-surface-700 whitespace-pre-wrap">{description}</p>}
    </div>
  );
}

function GoalSection({ entity }: { entity: Entity }) {
  const p = entity.properties;
  const level = (p.level as string) ?? "team";
  const status = (p.status as string) ?? "active";
  const owner = (p.owner_email as string) ?? null;
  const start = (p.time_bound_start as string) ?? null;
  const end = (p.time_bound_end as string) ?? null;
  const target = (p.target_value as number) ?? null;
  const current = (p.current_value as number) ?? null;
  const krs = (p.key_results as Array<{ title: string; target_value: number; current_value: number; unit: string }>) ?? [];
  const progress = target && target > 0 && current != null ? Math.round((current / target) * 100) : 0;

  return (
    <div className="card space-y-4">
      <h2 className="font-semibold text-surface-900">Goal Details</h2>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div><span className="text-surface-500">Level:</span> <span className="badge bg-purple-100 text-purple-700 capitalize">{level}</span></div>
        <div><span className="text-surface-500">Status:</span> <span className="capitalize">{status}</span></div>
        {owner && <div><span className="text-surface-500">Owner:</span> {owner}</div>}
        {start && end && <div><span className="text-surface-500">Timeline:</span> {new Date(start).toLocaleDateString()} &mdash; {new Date(end).toLocaleDateString()}</div>}
      </div>
      {target != null && (
        <div>
          <div className="flex items-center justify-between text-xs text-surface-500 mb-1">
            <span>{current ?? 0} / {target}</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-surface-100">
            <div className="h-full rounded-full bg-purple-600 transition-all" style={{ width: `${Math.min(progress, 100)}%` }} />
          </div>
        </div>
      )}
      {krs.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-surface-700">Key Results</h3>
          {krs.map((kr, i) => {
            const krProgress = kr.target_value > 0 ? Math.round((kr.current_value / kr.target_value) * 100) : 0;
            return (
              <div key={i} className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-surface-700">{kr.title}</span>
                  <span className="text-surface-500">{krProgress}%</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-100">
                  <div className="h-full rounded-full bg-purple-500" style={{ width: `${Math.min(krProgress, 100)}%` }} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ProjectSection({ entity }: { entity: Entity }) {
  const p = entity.properties;
  const status = (p.status as string) ?? "active";
  const owner = (p.owner_email as string) ?? null;
  const start = (p.start_date as string) ?? null;
  const end = (p.end_date as string) ?? null;
  const description = (p.description as string) ?? null;

  return (
    <div className="card space-y-3">
      <h2 className="font-semibold text-surface-900">Project Details</h2>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div><span className="text-surface-500">Status:</span> <span className="badge bg-green-100 text-green-700 capitalize">{status}</span></div>
        {owner && <div><span className="text-surface-500">Owner:</span> {owner}</div>}
        {start && end && <div className="col-span-2"><span className="text-surface-500">Timeline:</span> {new Date(start).toLocaleDateString()} &mdash; {new Date(end).toLocaleDateString()}</div>}
      </div>
      {description && <p className="text-sm text-surface-700">{description}</p>}
    </div>
  );
}

function PersonSection({ entity }: { entity: Entity }) {
  const p = entity.properties;
  const email = (p.email as string) ?? null;
  const role = (p.role as string) ?? null;
  const github = (p.github_username as string) ?? null;

  return (
    <div className="card space-y-3">
      <h2 className="font-semibold text-surface-900">Person Details</h2>
      <div className="grid grid-cols-2 gap-3 text-sm">
        {email && <div><span className="text-surface-500">Email:</span> {email}</div>}
        {role && <div><span className="text-surface-500">Role:</span> {role}</div>}
        {github && (
          <div>
            <span className="text-surface-500">GitHub:</span>{" "}
            <a href={`https://github.com/${github}`} target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline">
              {github} <ExternalLink size={12} className="inline" />
            </a>
          </div>
        )}
      </div>
    </div>
  );
}

function PrSection({ entity }: { entity: Entity }) {
  const p = entity.properties;
  const status = (p.status as string) ?? "open";
  const author = (p.author as string) ?? null;
  const reviewsPending = (p.reviews_pending as number) ?? 0;
  const sourceUrl = (p.source_url as string) ?? null;

  return (
    <div className="card space-y-3">
      <h2 className="font-semibold text-surface-900">Pull Request Details</h2>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div><span className="text-surface-500">Status:</span> <span className="badge bg-cyan-100 text-cyan-700 capitalize">{status}</span></div>
        {author && <div><span className="text-surface-500">Author:</span> {author}</div>}
        <div><span className="text-surface-500">Reviews pending:</span> {reviewsPending}</div>
        {p.additions != null && <div><span className="text-surface-500">Changes:</span> +{String(p.additions)} / -{String(p.deletions ?? 0)}</div>}
      </div>
      {sourceUrl && (
        <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-sm text-primary-600 hover:underline">
          View on GitHub <ExternalLink size={14} />
        </a>
      )}
    </div>
  );
}

function TypeSpecificSection({ entity }: { entity: Entity }) {
  switch (entity.type) {
    case EntityType.TASK: return <TaskSection entity={entity} />;
    case EntityType.GOAL: return <GoalSection entity={entity} />;
    case EntityType.PROJECT: return <ProjectSection entity={entity} />;
    case EntityType.PERSON: return <PersonSection entity={entity} />;
    case EntityType.COMMIT_PR: return <PrSection entity={entity} />;
    default: return null;
  }
}

// ── Connections Panel ──

const edgeLabels: Record<string, { outgoing: string; incoming: string }> = {
  owns: { outgoing: "Owns", incoming: "Owned by" },
  blocks: { outgoing: "Blocks", incoming: "Blocked by" },
  depends_on: { outgoing: "Depends on", incoming: "Depended on by" },
  authored: { outgoing: "Authored", incoming: "Authored by" },
  mentioned_in: { outgoing: "Mentioned in", incoming: "Mentions" },
  tagged_to: { outgoing: "Tagged to", incoming: "Tagged from" },
  contains: { outgoing: "Contains", incoming: "Contained in" },
  parent_of: { outgoing: "Parent of", incoming: "Child of" },
  assigned_to: { outgoing: "Assigned to", incoming: "Assigned from" },
  ships_to: { outgoing: "Ships to", incoming: "Shipped from" },
  caused_by: { outgoing: "Caused by", incoming: "Causes" },
  conflicts_with: { outgoing: "Conflicts with", incoming: "Conflicts with" },
  measures: { outgoing: "Measures", incoming: "Measured by" },
};

interface EdgeGroup {
  label: string;
  entities: Entity[];
}

function ConnectionsPanel({ entityId, edges, entityMap }: { entityId: string; edges: Edge[]; entityMap: Map<string, Entity> }) {
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  const groups = useMemo(() => {
    const result: Record<string, EdgeGroup> = {};

    for (const edge of edges) {
      const isOutgoing = edge.from_entity_id === entityId;
      const otherId = isOutgoing ? edge.to_entity_id : edge.from_entity_id;
      const otherEntity = entityMap.get(otherId);
      if (!otherEntity) continue;

      const labels = edgeLabels[edge.type];
      const label = labels ? (isOutgoing ? labels.outgoing : labels.incoming) : edge.type;
      const key = `${edge.type}-${isOutgoing ? "out" : "in"}`;

      if (!result[key]) {
        result[key] = { label, entities: [] };
      }
      // Avoid duplicates
      if (!result[key].entities.find(e => e.id === otherEntity.id)) {
        result[key].entities.push(otherEntity);
      }
    }

    return result;
  }, [edges, entityId, entityMap]);

  const groupEntries = Object.entries(groups);

  if (groupEntries.length === 0) {
    return (
      <div className="card">
        <h2 className="font-semibold text-surface-900">Connections</h2>
        <p className="mt-2 text-sm text-surface-500">No connections found.</p>
      </div>
    );
  }

  const toggleGroup = (key: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  // Start all groups expanded
  const allExpanded = expandedGroups.size === 0;

  return (
    <div className="card">
      <h2 className="font-semibold text-surface-900 mb-4">Connections</h2>
      <div className="space-y-3">
        {groupEntries.map(([key, group]) => {
          const isExpanded = allExpanded || expandedGroups.has(key);
          return (
            <div key={key}>
              <button
                onClick={() => toggleGroup(key)}
                className="flex items-center gap-2 text-sm font-medium text-surface-700 hover:text-surface-900 w-full text-left"
              >
                {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                {group.label} ({group.entities.length})
              </button>
              {isExpanded && (
                <div className="mt-2 ml-5 space-y-2">
                  {group.entities.map((ent) => (
                    <EntityCard key={ent.id} entity={ent} />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Properties Section ──

function PropertiesSection({ properties }: { properties: Record<string, unknown> }) {
  const [expanded, setExpanded] = useState(false);
  const entries = Object.entries(properties);

  if (entries.length === 0) return null;

  return (
    <div className="card">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 font-semibold text-surface-900 w-full text-left"
      >
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        Properties ({entries.length})
      </button>
      {expanded && (
        <dl className="mt-3 space-y-2 text-sm">
          {entries.map(([key, value]) => (
            <div key={key} className="flex gap-2">
              <dt className="font-medium text-surface-500 min-w-[140px] shrink-0">{key}:</dt>
              <dd className="text-surface-700 break-all">
                {typeof value === "object" ? (
                  <pre className="text-xs bg-surface-50 rounded p-1 overflow-auto max-h-40">{JSON.stringify(value, null, 2)}</pre>
                ) : (
                  String(value)
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

// ── Main Page ──

export function EntityDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: detail, isPending: loading, error } = useEntity(id!);
  const { data: neighborhood } = useGraphNeighborhood(id!, 1);

  const entityMap = useMemo(() => {
    const map = new Map<string, Entity>();
    for (const e of (neighborhood?.entities ?? [])) {
      map.set(e.id, e);
    }
    return map;
  }, [neighborhood]);

  // Merge edges from detail and neighborhood
  const allEdges = useMemo(() => {
    const edgeMap = new Map<string, Edge>();
    if (detail?.edges) {
      for (const e of detail.edges) edgeMap.set(e.id, e);
    }
    for (const e of (neighborhood?.edges ?? [])) {
      edgeMap.set(e.id, e);
    }
    return Array.from(edgeMap.values());
  }, [detail, neighborhood]);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-4 w-32 bg-surface-200 rounded animate-pulse" />
        <div className="h-8 w-96 bg-surface-200 rounded animate-pulse" />
        <div className="h-4 w-64 bg-surface-100 rounded animate-pulse" />
        <div className="card animate-pulse h-48" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1 text-sm text-surface-500 hover:text-primary-600">
          <ArrowLeft size={14} />
          Back
        </button>
        <div className="card">
          <p className="text-sm text-red-600">
            {error?.message ?? "Entity not found."}
          </p>
        </div>
      </div>
    );
  }

  const { entity } = detail;

  return (
    <div className="space-y-6">
      <EntityHeader entity={entity} />
      <TypeSpecificSection entity={entity} />
      <ConnectionsPanel entityId={entity.id} edges={allEdges} entityMap={entityMap} />
      <PropertiesSection properties={entity.properties} />
    </div>
  );
}
