import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useOrgContext } from "@/contexts/OrgContext";
import * as api from "@/services/api";
import { useGoals } from "@/hooks/queries";
import { Input } from "@/components/ui/input";
import { Target, X, Plus, Loader2 } from "lucide-react";
import { Link } from "react-router-dom";

interface PrdLinkPanelProps {
  prdId: string;
}

export function PrdLinkPanel({ prdId }: PrdLinkPanelProps) {
  const { orgId } = useOrgContext();
  const qc = useQueryClient();

  // Fetch edges for this PRD to find linked goals and projects
  const { data: edges, isLoading } = useQuery({
    queryKey: ["prdLinks", orgId, prdId],
    queryFn: () => api.getEntityEdges(prdId, "outgoing"),
    enabled: !!orgId && !!prdId,
  });

  // Filter to TAGGED_TO edges (goals/projects)
  const linkedEdges = (edges ?? []).filter((e) => e.type === "tagged_to");

  const linkMutation = useMutation({
    mutationFn: ({ targetId, edgeType }: { targetId: string; edgeType: string }) =>
      api.createEdge({
        from_entity_id: prdId,
        to_entity_id: targetId,
        type: edgeType,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdLinks", orgId, prdId] });
      qc.invalidateQueries({ queryKey: ["wiki"] });
    },
  });

  const unlinkMutation = useMutation({
    mutationFn: ({ targetId, edgeType }: { targetId: string; edgeType: string }) =>
      api.deleteEdge({
        from_entity_id: prdId,
        to_entity_id: targetId,
        type: edgeType,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["prdLinks", orgId, prdId] });
      qc.invalidateQueries({ queryKey: ["wiki"] });
    },
  });

  if (isLoading) {
    return <Loader2 className="h-4 w-4 animate-spin text-surface-400" />;
  }

  return (
    <div className="space-y-3">
      {/* Linked entities */}
      {linkedEdges.length > 0 && (
        <div className="space-y-1">
          {linkedEdges.map((edge) => (
            <div
              key={`${edge.from_entity_id}-${edge.to_entity_id}`}
              className="flex items-center gap-2 rounded-md bg-surface-50 px-2 py-1"
            >
              <Target className="h-3.5 w-3.5 shrink-0 text-amber-600" />
              <Link
                to={`/goals/${edge.to_entity_id}`}
                className="flex-1 truncate text-xs text-surface-700 hover:text-primary-600"
              >
                {edge.to_entity_id.slice(0, 8)}...
              </Link>
              <button
                type="button"
                onClick={() =>
                  unlinkMutation.mutate({ targetId: edge.to_entity_id, edgeType: edge.type })
                }
                className="shrink-0 rounded p-0.5 text-surface-400 hover:bg-surface-200 hover:text-surface-600"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Add link */}
      <LinkGoalDropdown
        existingIds={new Set(linkedEdges.map((e) => e.to_entity_id))}
        onLink={(goalId) => linkMutation.mutate({ targetId: goalId, edgeType: "tagged_to" })}
        isLinking={linkMutation.isPending}
      />
    </div>
  );
}

function LinkGoalDropdown({
  existingIds,
  onLink,
  isLinking,
}: {
  existingIds: Set<string>;
  onLink: (goalId: string) => void;
  isLinking: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const { data: goals } = useGoals();

  const available = (goals ?? []).filter(
    (g) => !existingIds.has(g.id) && g.title.toLowerCase().includes(search.toLowerCase()),
  );

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="inline-flex items-center gap-1 rounded-md border border-dashed border-surface-300 px-2 py-1 text-xs text-surface-400 transition-colors hover:border-surface-400 hover:text-surface-500"
      >
        <Plus className="h-3 w-3" />
        Link Goal
      </button>
    );
  }

  return (
    <div className="space-y-1.5">
      <Input
        autoFocus
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setIsOpen(false);
            setSearch("");
          }
        }}
        placeholder="Search goals..."
        className="h-7 text-xs"
      />
      <div className="max-h-32 overflow-y-auto rounded-md border border-surface-200 bg-white">
        {available.length === 0 ? (
          <p className="px-2 py-1.5 text-xs text-surface-400">No goals found</p>
        ) : (
          available.slice(0, 8).map((g) => (
            <button
              key={g.id}
              type="button"
              disabled={isLinking}
              onClick={() => {
                onLink(g.id);
                setIsOpen(false);
                setSearch("");
              }}
              className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs transition-colors hover:bg-surface-50"
            >
              <Target className="h-3 w-3 shrink-0 text-amber-500" />
              <span className="truncate">{g.title}</span>
            </button>
          ))
        )}
      </div>
      <button
        type="button"
        onClick={() => {
          setIsOpen(false);
          setSearch("");
        }}
        className="text-xs text-surface-400 hover:text-surface-600"
      >
        Cancel
      </button>
    </div>
  );
}
