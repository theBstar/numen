import { useState } from "react";
import { cn } from "@/lib/utils";
import { useMembers } from "@/hooks/queries";
import { usePrdStakeholders } from "@/hooks/prdQueries";
import {
  useAddStakeholder,
  useRemoveStakeholder,
} from "@/hooks/prdMutations";
import type { OrgMember } from "@/types";
import { Plus, X, Crown, Eye, UserCheck } from "lucide-react";

interface PrdStakeholderListProps {
  prdId: string;
  isOwner: boolean;
}

const ROLE_CONFIG: { [key: string]: { icon: typeof Crown; label: string; color: string } } = {
  owner: {
    icon: Crown,
    label: "Owner",
    color: "text-amber-600",
  },
  stakeholder: {
    icon: Eye,
    label: "Stakeholder",
    color: "text-blue-600",
  },
  reviewer: {
    icon: UserCheck,
    label: "Reviewer",
    color: "text-purple-600",
  },
};

function MemberSearchDropdown({
  onSelect,
  onClose,
  existingMemberIds,
}: {
  onSelect: (memberId: string) => void;
  onClose: () => void;
  existingMemberIds: Set<string>;
}) {
  const [search, setSearch] = useState("");
  const { data: members } = useMembers();

  const filteredMembers = (members ?? []).filter((m: OrgMember) => {
    if (existingMemberIds.has(m.id)) return false;
    const query = search.toLowerCase();
    if (!query) return true;
    return (
      (m.display_name ?? "").toLowerCase().includes(query) ||
      m.email.toLowerCase().includes(query)
    );
  });

  return (
    <div className="absolute left-0 top-full z-10 mt-1 w-64 rounded-md border border-surface-200 bg-white shadow-lg">
      <div className="p-2">
        <input
          autoFocus
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search members..."
          className="w-full rounded-md border border-surface-200 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
          }}
        />
      </div>
      <div className="max-h-48 overflow-y-auto">
        {filteredMembers.length === 0 ? (
          <p className="px-3 py-2 text-xs text-surface-400">No members found</p>
        ) : (
          filteredMembers.map((m: OrgMember) => (
            <button
              key={m.id}
              type="button"
              onClick={() => {
                onSelect(m.id);
                onClose();
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-surface-50"
            >
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-surface-100 text-xs font-medium text-surface-600">
                {(m.display_name ?? m.email)[0]?.toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-surface-700">
                  {m.display_name ?? m.email.split("@")[0]}
                </p>
                <p className="truncate text-xs text-surface-400">{m.email}</p>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

export function PrdStakeholderList({
  prdId,
  isOwner,
}: PrdStakeholderListProps) {
  const { data: stakeholdersData } = usePrdStakeholders(prdId);
  const addStakeholder = useAddStakeholder(prdId);
  const removeStakeholder = useRemoveStakeholder(prdId);

  const [showAddDropdown, setShowAddDropdown] = useState(false);

  const stakeholders = stakeholdersData?.items ?? [];

  // Build set of existing member IDs to exclude from search
  const existingMemberIds = new Set(
    stakeholders
      .filter((s) => s.member_id != null)
      .map((s) => s.member_id as string),
  );

  return (
    <div className="space-y-1.5">
      {stakeholders.length === 0 ? (
        <p className="text-xs italic text-surface-400">
          No stakeholders yet
        </p>
      ) : (
        stakeholders.map((stakeholder) => {
          const config = ROLE_CONFIG[stakeholder.role_type] ?? ROLE_CONFIG["stakeholder"];
          if (!config) return null;
          const Icon = config.icon;

          return (
            <div
              key={stakeholder.person_id}
              className="flex items-center justify-between rounded-md px-2 py-1.5 transition-colors hover:bg-surface-50"
            >
              <div className="flex items-center gap-2">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-surface-100 text-xs font-medium text-surface-600">
                  {stakeholder.person_name[0]?.toUpperCase()}
                </div>
                <div className="min-w-0">
                  <span className="text-sm text-surface-700">
                    {stakeholder.person_name}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="flex items-center gap-1">
                  <Icon className={cn("h-3 w-3", config.color)} />
                  <span className={cn("text-xs", config.color)}>
                    {config.label}
                  </span>
                </div>
                {isOwner && stakeholder.role_type === "stakeholder" && stakeholder.member_id && (
                  <button
                    type="button"
                    onClick={() => removeStakeholder.mutate(stakeholder.member_id!)}
                    className="rounded p-0.5 text-surface-300 transition-colors hover:bg-surface-100 hover:text-surface-500"
                    title="Remove stakeholder"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>
          );
        })
      )}

      {/* Add stakeholder button */}
      {isOwner && (
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowAddDropdown(!showAddDropdown)}
            className="inline-flex items-center gap-1 rounded-md border border-dashed border-surface-300 px-2 py-1 text-xs text-surface-400 transition-colors hover:border-surface-400 hover:text-surface-500"
          >
            <Plus className="h-3 w-3" />
            Add Stakeholder
          </button>
          {showAddDropdown && (
            <MemberSearchDropdown
              onSelect={(id) => addStakeholder.mutate(id)}
              onClose={() => setShowAddDropdown(false)}
              existingMemberIds={existingMemberIds}
            />
          )}
        </div>
      )}
    </div>
  );
}
