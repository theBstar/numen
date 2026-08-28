import { RefreshCw, Cable } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { BriefingCard } from "@/components/BriefingCard";
import { EmptyState } from "@/components/EmptyState";
import type { Briefing, BriefingItem } from "@/types";

interface BriefingSectionProps {
  briefing: Briefing | null;
  loading: boolean;
  generating: boolean;
  connectedCount: number;
  connectorsLoading: boolean;
  onGenerate: () => void;
}

type SignalGroup = {
  label: string;
  items: BriefingItem[];
};

function groupBySignalType(items: BriefingItem[]): SignalGroup[] {
  const groups: Record<string, BriefingItem[]> = {};

  for (const item of items) {
    const type = item.entity_type;
    let groupKey: string;

    if (type === "task" && item.urgency_score >= 70) {
      groupKey = "Urgent";
    } else if (type === "commit_pr") {
      groupKey = "Code Reviews";
    } else if (type === "incident" || type === "error_event") {
      groupKey = "Incidents";
    } else if (type === "goal") {
      groupKey = "Goals";
    } else if (type === "feature") {
      groupKey = "Features";
    } else {
      groupKey = "Work Items";
    }

    if (!groups[groupKey]) groups[groupKey] = [];
    groups[groupKey]!.push(item);
  }

  // Sort groups: Urgent first, then by item count
  const order = ["Urgent", "Incidents", "Code Reviews", "Goals", "Features", "Work Items"];
  return order
    .filter((key) => groups[key] && groups[key].length > 0)
    .map((key) => ({ label: key, items: groups[key] as BriefingItem[] }));
}

export function BriefingSection({
  briefing,
  loading,
  generating,
  connectedCount,
  connectorsLoading,
  onGenerate,
}: BriefingSectionProps) {
  const navigate = useNavigate();

  const sortedItems = briefing
    ? [...briefing.items]
        .sort((a, b) => b.urgency_score - a.urgency_score)
        .slice(0, 7)
    : [];

  const groups = groupBySignalType(sortedItems);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-surface-900">Today's Briefing</h2>
        <button
          onClick={onGenerate}
          disabled={generating}
          className="flex items-center gap-2 text-sm text-surface-400 hover:text-primary-600 transition-colors disabled:opacity-50"
          title="Regenerate briefing"
        >
          <RefreshCw size={14} className={generating ? "animate-spin" : ""} />
          <span>
            {generating
              ? "Generating..."
              : briefing
                ? `Updated ${new Date(briefing.generated_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                : "Generate"}
          </span>
        </button>
      </div>

      {loading || generating || connectorsLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="card animate-pulse">
              <div className="h-4 w-3/4 rounded bg-surface-200" />
              <div className="mt-2 h-3 w-full rounded bg-surface-100" />
            </div>
          ))}
        </div>
      ) : sortedItems.length > 0 ? (
        <div className="space-y-4">
          {groups.map((group) => (
            <div key={group.label}>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-surface-400 mb-2">
                {group.label}
              </h3>
              <div className="space-y-2">
                {group.items.map((item, idx) => (
                  <BriefingCard key={`${item.entity_id}-${idx}`} item={item} />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : connectedCount === 0 ? (
        <EmptyState
          icon={Cable}
          title="Connect your first integration"
          description="Link Linear, GitHub, or Slack to see your daily briefing with prioritized recommendations."
          action={{ label: "Go to Connections", onClick: () => navigate("/connections") }}
        />
      ) : briefing?.empty_reason === "no_person_entity" ? (
        <div className="card text-center py-8">
          <p className="text-sm text-surface-500">
            We couldn't match you to a person in the graph yet. Sync a connector
            that includes you (GitHub, Linear) and try again.
          </p>
          <button onClick={onGenerate} disabled={generating} className="btn-primary mt-3">
            Try again
          </button>
        </div>
      ) : briefing?.empty_reason === "no_urgent_signals" ? (
        <div className="card text-center py-8">
          <p className="text-sm text-surface-500">
            Nothing urgent for you right now. We'll surface new work as connectors sync.
          </p>
          <button onClick={onGenerate} disabled={generating} className="btn-primary mt-3">
            Regenerate
          </button>
        </div>
      ) : (
        <div className="card text-center py-8">
          <p className="text-sm text-surface-500">No briefing available yet.</p>
          <button onClick={onGenerate} disabled={generating} className="btn-primary mt-3">
            Generate Briefing
          </button>
        </div>
      )}
    </div>
  );
}
