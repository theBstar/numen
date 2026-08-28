import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, GitMerge, X, UserCheck, Link2, AlertTriangle, ChevronDown } from "lucide-react";
import {
  getPersonResolutions,
  mergeResolution,
  markResolutionDistinct,
  dismissResolution,
  linkResolution,
  getEntities,
} from "@/services/api";
import type { PersonResolution, Entity } from "@/types";

const SOURCE_LABELS: Record<string, string> = {
  github: "GitHub",
  linear: "Linear",
  slack: "Slack",
  manual: "Manual",
  notion: "Notion",
};

const SOURCE_COLORS: Record<string, string> = {
  github: "bg-gray-800 text-white",
  linear: "bg-indigo-600 text-white",
  slack: "bg-green-600 text-white",
  manual: "bg-zinc-500 text-white",
};

const REASON_LABELS: Record<string, string> = {
  email: "Email match",
  github_username: "GitHub username match",
  slack_id: "Slack ID match",
  exact_name: "Exact name match",
  fuzzy_name: "Similar name",
};

function getInitials(name: string): string {
  return name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

function ConfidenceBadge({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  const color =
    pct >= 80
      ? "bg-red-100 text-red-700"
      : pct >= 60
        ? "bg-amber-100 text-amber-700"
        : "bg-zinc-100 text-zinc-600";
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {pct}% match
    </span>
  );
}

function PersonCard({ entity, label }: { entity: Entity; label: string }) {
  const name = entity.canonical_name;
  const source = entity.source;
  const email =
    (entity.source_ids?.email as string) ||
    (entity.properties?.email as string) ||
    "";
  const github =
    (entity.source_ids?.github as string) ||
    (entity.source_ids?.github_username as string) ||
    (entity.properties?.login as string) ||
    "";

  return (
    <div className="flex-1 min-w-0">
      <p className="text-[11px] font-medium text-zinc-400 uppercase tracking-wider mb-2">
        {label}
      </p>
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-zinc-200 flex items-center justify-center text-sm font-semibold text-zinc-600 shrink-0">
          {getInitials(name)}
        </div>
        <div className="min-w-0">
          <p className="font-medium text-zinc-900 truncate">{name}</p>
          <div className="flex items-center gap-2 mt-0.5">
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${SOURCE_COLORS[source] || "bg-zinc-200 text-zinc-700"}`}
            >
              {SOURCE_LABELS[source] || source}
            </span>
            {email && (
              <span className="text-xs text-zinc-500 truncate">{email}</span>
            )}
          </div>
          {github && (
            <p className="text-xs text-zinc-400 mt-0.5">@{github}</p>
          )}
        </div>
      </div>
    </div>
  );
}

function ResolutionCard({
  resolution,
  onAction,
  isActing,
  people,
}: {
  resolution: PersonResolution;
  onAction: (
    id: string,
    action: "merge" | "distinct" | "dismiss" | "link",
    targetId?: string,
  ) => void;
  isActing: boolean;
  people: Entity[];
}) {
  const [showLinkPicker, setShowLinkPicker] = useState(false);
  const [linkSearch, setLinkSearch] = useState("");

  const filteredPeople = people.filter(
    (p) =>
      p.id !== resolution.candidate.id &&
      p.id !== resolution.match.id &&
      p.canonical_name.toLowerCase().includes(linkSearch.toLowerCase()),
  );

  return (
    <div className="bg-white border border-zinc-200 rounded-lg p-5 hover:border-zinc-300 transition-colors">
      <div className="flex items-start gap-4">
        {/* Candidate */}
        <PersonCard entity={resolution.candidate} label="New from sync" />

        {/* Match indicator */}
        <div className="flex flex-col items-center gap-1 pt-6 shrink-0">
          <div className="w-8 h-px bg-zinc-300" />
          <ConfidenceBadge confidence={resolution.confidence} />
          <div className="w-8 h-px bg-zinc-300" />
        </div>

        {/* Match */}
        <PersonCard entity={resolution.match} label="Existing person" />
      </div>

      {/* Match reasons */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {resolution.match_reasons.map((reason, i) => (
          <span
            key={i}
            className="inline-flex items-center gap-1 px-2 py-1 bg-zinc-50 border border-zinc-200 rounded text-xs text-zinc-600"
          >
            <span className="font-medium">
              {REASON_LABELS[reason.type] || reason.type}:
            </span>
            <span className="text-zinc-500">{reason.value}</span>
          </span>
        ))}
      </div>

      {/* Actions */}
      <div className="mt-4 flex items-center gap-2 border-t border-zinc-100 pt-3">
        <button
          onClick={() => onAction(resolution.id, "merge")}
          disabled={isActing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          <GitMerge className="w-3.5 h-3.5" />
          Merge
        </button>
        <button
          onClick={() => onAction(resolution.id, "distinct")}
          disabled={isActing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-zinc-300 text-zinc-700 text-sm font-medium rounded hover:bg-zinc-50 disabled:opacity-50 transition-colors"
        >
          <UserCheck className="w-3.5 h-3.5" />
          Different People
        </button>
        <button
          onClick={() => onAction(resolution.id, "dismiss")}
          disabled={isActing}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-zinc-300 text-zinc-700 text-sm font-medium rounded hover:bg-zinc-50 disabled:opacity-50 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
          Dismiss
        </button>
        <div className="relative">
          <button
            onClick={() => setShowLinkPicker(!showLinkPicker)}
            disabled={isActing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white border border-zinc-300 text-zinc-700 text-sm font-medium rounded hover:bg-zinc-50 disabled:opacity-50 transition-colors"
          >
            <Link2 className="w-3.5 h-3.5" />
            Link to Other
            <ChevronDown className="w-3 h-3" />
          </button>
          {showLinkPicker && (
            <div className="absolute top-full left-0 mt-1 w-72 bg-white border border-zinc-200 rounded-lg shadow-lg z-20 p-2">
              <input
                type="text"
                placeholder="Search people..."
                value={linkSearch}
                onChange={(e) => setLinkSearch(e.target.value)}
                className="w-full px-2 py-1.5 border border-zinc-200 rounded text-sm mb-1 focus:outline-none focus:ring-1 focus:ring-blue-500"
                autoFocus
              />
              <div className="max-h-48 overflow-y-auto">
                {filteredPeople.slice(0, 10).map((p) => (
                  <button
                    key={p.id}
                    onClick={() => {
                      onAction(resolution.id, "link", p.id);
                      setShowLinkPicker(false);
                    }}
                    className="w-full text-left px-2 py-1.5 text-sm hover:bg-zinc-50 rounded flex items-center gap-2"
                  >
                    <div className="w-6 h-6 rounded-full bg-zinc-200 flex items-center justify-center text-[10px] font-semibold text-zinc-600">
                      {getInitials(p.canonical_name)}
                    </div>
                    <span className="truncate">{p.canonical_name}</span>
                  </button>
                ))}
                {filteredPeople.length === 0 && (
                  <p className="text-xs text-zinc-400 px-2 py-3 text-center">
                    No matching people found
                  </p>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PersonResolutions() {
  const [resolutions, setResolutions] = useState<PersonResolution[]>([]);
  const [people, setPeople] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(true);
  const [actingOn, setActingOn] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [res, entities] = await Promise.all([
        getPersonResolutions("pending"),
        getEntities({ type: "person", page_size: 200 }),
      ]);
      setResolutions(res);
      setPeople(entities.items);
    } catch (err) {
      console.error("Failed to load resolutions:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleAction = useCallback(
    async (
      id: string,
      action: "merge" | "distinct" | "dismiss" | "link",
      targetId?: string,
    ) => {
      setActingOn(id);
      try {
        if (action === "merge") {
          await mergeResolution(id);
        } else if (action === "distinct") {
          await markResolutionDistinct(id);
        } else if (action === "dismiss") {
          await dismissResolution(id);
        } else if (action === "link" && targetId) {
          await linkResolution(id, targetId);
        }
        // Remove from list after successful action
        setResolutions((prev) => prev.filter((r) => r.id !== id));
      } catch (err) {
        console.error(`Failed to ${action} resolution:`, err);
      } finally {
        setActingOn(null);
      }
    },
    [],
  );

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-zinc-200 rounded w-64" />
          <div className="h-32 bg-zinc-100 rounded" />
          <div className="h-32 bg-zinc-100 rounded" />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="mb-6">
        <Link
          to="/people"
          className="inline-flex items-center gap-1 text-sm text-zinc-500 hover:text-zinc-700 mb-3"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to People
        </Link>
        <h1 className="text-2xl font-bold text-zinc-900">
          Resolve Duplicate People
        </h1>
        <p className="text-sm text-zinc-500 mt-1">
          When tools are synced, the same person may appear under different names
          or accounts. Review these potential matches and decide how to handle
          them.
        </p>
      </div>

      {/* Resolutions */}
      {resolutions.length === 0 ? (
        <div className="text-center py-16 bg-white border border-zinc-200 rounded-lg">
          <AlertTriangle className="w-10 h-10 text-zinc-300 mx-auto mb-3" />
          <p className="text-zinc-500 font-medium">
            No pending duplicates to resolve
          </p>
          <p className="text-sm text-zinc-400 mt-1">
            Duplicates will appear here after syncing your connected tools.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-sm text-zinc-500">
            {resolutions.length} potential{" "}
            {resolutions.length === 1 ? "duplicate" : "duplicates"} found
          </p>
          {resolutions.map((r) => (
            <ResolutionCard
              key={r.id}
              resolution={r}
              onAction={handleAction}
              isActing={actingOn === r.id}
              people={people}
            />
          ))}
        </div>
      )}
    </div>
  );
}
