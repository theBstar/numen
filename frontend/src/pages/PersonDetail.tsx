import { useState, useEffect, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Mail, Clock, Shield } from "lucide-react";
import { useOrgContext } from "@/contexts/OrgContext";
import { useEntity, useGraphNeighborhood } from "@/hooks/queries";
import { getMemberByPersonEntityId, updateMember } from "@/services/api";
import { EntityCard } from "@/components/EntityCard";
import type { OrgMember, Entity, Edge } from "@/types";
import { cn, formatDate } from "@/lib/utils";

const ROLE_OPTIONS = [
  { value: "engineer", label: "Engineer" },
  { value: "pm", label: "PM" },
  { value: "em", label: "EM" },
  { value: "designer", label: "Designer" },
  { value: "cto", label: "CTO" },
  { value: "vp_eng", label: "VP Eng" },
  { value: "vp_product", label: "VP Product" },
];

const ROLE_COLORS: Record<string, string> = {
  engineer: "bg-blue-100 text-blue-700",
  pm: "bg-purple-100 text-purple-700",
  em: "bg-amber-100 text-amber-700",
  cto: "bg-red-100 text-red-700",
  designer: "bg-pink-100 text-pink-700",
  vp_eng: "bg-red-50 text-red-600",
  vp_product: "bg-purple-50 text-purple-600",
};

const AVATAR_COLORS: Record<string, string> = {
  engineer: "bg-blue-500",
  pm: "bg-purple-500",
  em: "bg-amber-500",
  cto: "bg-red-500",
  designer: "bg-pink-500",
  vp_eng: "bg-red-400",
  vp_product: "bg-purple-400",
};

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

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
  reports_to: { outgoing: "Reports to", incoming: "Manages" },
  ships_to: { outgoing: "Ships to", incoming: "Shipped from" },
  caused_by: { outgoing: "Caused by", incoming: "Causes" },
  conflicts_with: { outgoing: "Conflicts with", incoming: "Conflicts with" },
  measures: { outgoing: "Measures", incoming: "Measured by" },
};

export function PersonDetail() {
  const { id } = useParams<{ id: string }>();
  const { isAdmin } = useOrgContext();
  const { data: entityDetail, isPending: entityLoading } = useEntity(id!);
  const { data: neighborhood } = useGraphNeighborhood(id!, 1);
  const [member, setMember] = useState<OrgMember | null>(null);
  const [memberLoading, setMemberLoading] = useState(true);
  const [roleUpdating, setRoleUpdating] = useState(false);

  useEffect(() => {
    if (!id) return;
    getMemberByPersonEntityId(id)
      .then(setMember)
      .catch(() => setMember(null))
      .finally(() => setMemberLoading(false));
  }, [id]);

  const entity = entityDetail?.entity ?? null;
  const props = (entity?.properties ?? {}) as Record<string, unknown>;
  const role = (props.role as string) ?? member?.role ?? "";
  const email = (props.email as string) ?? member?.email ?? "";
  const title = (props.title as string) ?? "";
  const team = (props.team as string) ?? "";
  const github = (props.github_username as string) ?? "";
  const displayName = entity?.canonical_name ?? member?.display_name ?? "";

  const entityMap = useMemo(() => {
    const map = new Map<string, Entity>();
    for (const e of neighborhood?.entities ?? []) {
      map.set(e.id, e);
    }
    return map;
  }, [neighborhood]);

  const allEdges = useMemo(() => {
    const edgeMap = new Map<string, Edge>();
    if (entityDetail?.edges) {
      for (const e of entityDetail.edges) edgeMap.set(e.id, e);
    }
    for (const e of neighborhood?.edges ?? []) {
      edgeMap.set(e.id, e);
    }
    return Array.from(edgeMap.values());
  }, [entityDetail, neighborhood]);

  const connectionGroups = useMemo(() => {
    if (!id) return {};
    const result: Record<string, { label: string; entities: Entity[] }> = {};
    for (const edge of allEdges) {
      const isOutgoing = edge.from_entity_id === id;
      const otherId = isOutgoing ? edge.to_entity_id : edge.from_entity_id;
      const otherEntity = entityMap.get(otherId);
      if (!otherEntity) continue;
      const labels = edgeLabels[edge.type];
      const label = labels ? (isOutgoing ? labels.outgoing : labels.incoming) : edge.type;
      const key = `${edge.type}-${isOutgoing ? "out" : "in"}`;
      if (!result[key]) result[key] = { label, entities: [] };
      if (!result[key].entities.find((e) => e.id === otherEntity.id)) {
        result[key].entities.push(otherEntity);
      }
    }
    return result;
  }, [allEdges, id, entityMap]);

  async function handleRoleChange(newRole: string) {
    if (!member) return;
    setRoleUpdating(true);
    try {
      const updated = await updateMember(member.id, { role: newRole });
      setMember(updated);
    } catch {
      // ignore
    } finally {
      setRoleUpdating(false);
    }
  }

  const loading = entityLoading || memberLoading;

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-4 w-32 rounded bg-surface-200 animate-pulse" />
        <div className="h-8 w-96 rounded bg-surface-200 animate-pulse" />
        <div className="card animate-pulse h-48" />
      </div>
    );
  }

  if (!entity && !member) {
    return (
      <div className="space-y-4">
        <Link to="/people" className="inline-flex items-center gap-1 text-sm text-surface-500 hover:text-primary-600">
          <ArrowLeft size={14} />
          Back to People
        </Link>
        <div className="card">
          <p className="text-sm text-red-600">Person not found.</p>
        </div>
      </div>
    );
  }

  const groupEntries = Object.entries(connectionGroups);

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link to="/people" className="inline-flex items-center gap-1 text-sm text-surface-500 hover:text-primary-600 transition-colors">
        <ArrowLeft size={14} />
        Back to People
      </Link>

      {/* Person header */}
      <div className="card">
        <div className="flex items-start gap-5">
          <div
            className={cn(
              "flex h-16 w-16 items-center justify-center rounded-full text-xl font-bold text-white shrink-0",
              AVATAR_COLORS[role] || "bg-surface-400",
            )}
          >
            {getInitials(displayName || "?")}
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-2xl font-bold text-surface-900">{displayName}</h1>
            {title && <p className="mt-0.5 text-surface-600">{title}</p>}
            <div className="mt-3 flex flex-wrap items-center gap-4 text-sm text-surface-500">
              {email && (
                <span className="inline-flex items-center gap-1.5">
                  <Mail size={14} />
                  {email}
                </span>
              )}
              {team && <span>Team: {team}</span>}
              {member?.timezone && (
                <span className="inline-flex items-center gap-1.5">
                  <Clock size={14} />
                  {member.timezone}
                </span>
              )}
              {entity && (
                <span>Joined {formatDate(entity.created_at)}</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Role section */}
      <div className="card">
        <h2 className="flex items-center gap-2 font-semibold text-surface-900">
          <Shield size={16} />
          Role
        </h2>
        <div className="mt-3">
          {isAdmin ? (
            <div className="flex items-center gap-3">
              <select
                value={role}
                onChange={(e) => handleRoleChange(e.target.value)}
                disabled={roleUpdating}
                className="rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100 disabled:opacity-50"
              >
                {ROLE_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
              {roleUpdating && <span className="text-xs text-surface-400">Updating...</span>}
            </div>
          ) : (
            <span
              className={cn(
                "inline-flex rounded-full px-3 py-1 text-sm font-medium",
                ROLE_COLORS[role] || "bg-surface-100 text-surface-600",
              )}
            >
              {ROLE_OPTIONS.find((o) => o.value === role)?.label || role}
            </span>
          )}
        </div>
      </div>

      {/* Person details */}
      {github && (
        <div className="card">
          <h2 className="font-semibold text-surface-900">Details</h2>
          <div className="mt-3 text-sm">
            <span className="text-surface-500">GitHub:</span>{" "}
            <a
              href={`https://github.com/${github}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 hover:underline"
            >
              {github}
            </a>
          </div>
        </div>
      )}

      {/* Connections */}
      {groupEntries.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-surface-900 mb-4">Connections</h2>
          <div className="space-y-4">
            {groupEntries.map(([key, group]) => (
              <div key={key}>
                <p className="text-sm font-medium text-surface-700 mb-2">
                  {group.label} ({group.entities.length})
                </p>
                <div className="ml-1 space-y-2">
                  {group.entities.map((ent) => (
                    <EntityCard key={ent.id} entity={ent} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
