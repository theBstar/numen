import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  useLatestBriefing,
  useConnectors,
  useDashboardSummary,
} from "@/hooks/queries";
import { triggerBriefing, getActivity } from "@/services/api";
import { getGreeting, formatDate } from "@/lib/utils";
import { useOrgContext } from "@/contexts/OrgContext";
import { trackBriefingViewed } from "@/analytics/events";
import { RoleType } from "@/types";
import type { ActivityEntry } from "@/types";

import {
  MetricsStrip,
  BriefingSection,
  SyncStatusCompact,
  MyTasksWidget,
  GoalProgressWidget,
  TeamWorkloadWidget,
  DelayedProjectsWidget,
  ActionsCollapsed,
} from "@/components/dashboard";

const ROLE_LABELS: Record<string, string> = {
  engineer: "Engineer",
  pm: "Product Manager",
  em: "Engineering Manager",
  cto: "CTO",
  vp_eng: "VP Engineering",
  vp_product: "VP Product",
  designer: "Designer",
};

export function Dashboard() {
  const { orgId, role } = useOrgContext();
  const { data: briefing, isPending: briefingLoading, refetch: refetchBriefing } = useLatestBriefing();
  const { data: connectors, isPending: connectorsLoading } = useConnectors();
  const { data: summary, isPending: summaryLoading, refetch: refetchSummary } = useDashboardSummary();

  const displayConnectors = connectors ?? [];
  const connectedCount = displayConnectors.filter((c) => c.connected).length;

  const [generating, setGenerating] = useState(false);
  const [autoTriggered, setAutoTriggered] = useState(false);
  const [activity, setActivity] = useState<ActivityEntry[]>([]);

  useEffect(() => {
    if (!briefing) return;
    const items = Array.isArray(briefing.items) ? briefing.items.length : 0;
    trackBriefingViewed({ briefingId: String(briefing.id), itemCount: items });
  }, [briefing?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load activity feed
  useEffect(() => {
    if (!orgId) return;
    getActivity(10)
      .then(setActivity)
      .catch(() => setActivity([]));
  }, [orgId]);

  // Auto-trigger briefing generation if none exists or if stale (>30 min old)
  useEffect(() => {
    if (briefingLoading || !orgId || autoTriggered) return;
    const isStale = briefing
      ? Date.now() - new Date(briefing.generated_at).getTime() > 30 * 60 * 1000
      : true;
    if (isStale) {
      setAutoTriggered(true);
      handleGenerate();
    }
  }, [briefingLoading, briefing, orgId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    try {
      await triggerBriefing();
      refetchBriefing();
    } catch (err) {
      console.error("Failed to generate briefing:", err);
    } finally {
      setGenerating(false);
    }
  }, [refetchBriefing]);

  const handleRefreshAll = useCallback(() => {
    handleGenerate();
    refetchSummary();
  }, [handleGenerate, refetchSummary]);

  const effectiveRole = summary?.role ?? role ?? "engineer";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900">{getGreeting()}</h1>
          <div className="mt-1 flex items-center gap-2">
            <p className="text-surface-500">{formatDate(new Date().toISOString())}</p>
            <span className="rounded-full bg-primary-100 px-2 py-0.5 text-[10px] font-medium text-primary-700">
              {ROLE_LABELS[effectiveRole] ?? effectiveRole}
            </span>
          </div>
        </div>
        <button
          onClick={handleRefreshAll}
          disabled={generating || summaryLoading}
          className="flex items-center gap-2 text-sm text-surface-400 hover:text-primary-600 transition-colors disabled:opacity-50"
          title="Refresh dashboard"
        >
          <RefreshCw size={14} className={(generating || summaryLoading) ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Zone 1: Metrics Strip */}
      {summary ? (
        <MetricsStrip summary={summary} />
      ) : summaryLoading ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="card animate-pulse h-20" />
          ))}
        </div>
      ) : null}

      {/* Zone 2 + 3: Main Content + Sidebar */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Zone 2: Briefing (2/3 width) */}
        <div className="lg:col-span-2">
          <BriefingSection
            briefing={briefing ?? null}
            loading={briefingLoading}
            generating={generating}
            connectedCount={connectedCount}
            connectorsLoading={connectorsLoading}
            onGenerate={handleGenerate}
          />
        </div>

        {/* Zone 3: Sidebar (1/3 width) */}
        <div className="space-y-4">
          {/* Role-specific widget */}
          <RoleSidebarWidget
            role={effectiveRole}
            summary={summary ?? null}
          />

          {/* Recent Activity - compact */}
          {activity.length > 0 && (
            <div className="card">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-surface-400 mb-2">
                Recent Activity
              </h3>
              <div className="space-y-1.5">
                {activity.slice(0, 4).map((a) => (
                  <ActivityRow key={a.id} entry={a} />
                ))}
              </div>
            </div>
          )}

          {/* Admin actions - collapsed with badge */}
          <ActionsCollapsed />

          {/* Sync status - compact */}
          <SyncStatusCompact connectors={displayConnectors} loading={connectorsLoading} />
        </div>
      </div>
    </div>
  );
}

function RoleSidebarWidget({
  role,
  summary,
}: {
  role: string;
  summary: import("@/types").DashboardSummary | null;
}) {
  switch (role) {
    case RoleType.ENGINEER:
    case RoleType.DESIGNER:
      return <MyTasksWidget />;

    case RoleType.PM:
    case RoleType.VP_PRODUCT:
      return <GoalProgressWidget />;

    case RoleType.EM:
      return summary?.team_workload ? (
        <TeamWorkloadWidget members={summary.team_workload} />
      ) : (
        <MyTasksWidget />
      );

    case RoleType.CTO:
    case RoleType.VP_ENG:
      return summary?.delayed_projects ? (
        <DelayedProjectsWidget projects={summary.delayed_projects} />
      ) : (
        <GoalProgressWidget />
      );

    default:
      return <MyTasksWidget />;
  }
}

function ActivityRow({ entry }: { entry: ActivityEntry }) {
  const details = entry.details || {};
  const action = entry.action;

  let label = action;
  if (action === "task_status_changed") {
    const taskName = (details.task_name as string) || "Task";
    const oldStatus = (details.old_status as string) || "?";
    const newStatus = (details.new_status as string) || "?";
    label = `${taskName}: ${oldStatus} - ${newStatus}`;
  }

  return (
    <div className="text-xs text-surface-600 flex items-start gap-2 py-0.5">
      <div className="shrink-0 mt-1 w-1 h-1 rounded-full bg-primary-400" />
      <div className="min-w-0">
        <p className="truncate">{label}</p>
        {entry.created_at && (
          <p className="text-surface-400 text-[10px]">{formatRelativeTime(entry.created_at)}</p>
        )}
      </div>
    </div>
  );
}

function formatRelativeTime(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
