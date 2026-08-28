import { Check, X, RefreshCw, Clock } from "lucide-react";
import type { ConnectorStatus } from "@/types";
import { cn, formatRelativeTime } from "@/lib/utils";

export const connectorMeta: Record<string, { name: string; color: string; description: string }> = {
  linear: { name: "Linear", color: "bg-violet-600", description: "Issues, projects, sprints, and blockers" },
  github: { name: "GitHub", color: "bg-gray-800", description: "PRs, commits, deploys, and code ownership" },
  slack: { name: "Slack", color: "bg-emerald-600", description: "Decisions, mentions, and communication patterns" },
  jira: { name: "Jira", color: "bg-sky-700", description: "Issues, projects, epics, and blockers" },
  notion: { name: "Notion", color: "bg-stone-800", description: "PRDs, specs, and document completeness" },
  gdocs: { name: "Google Docs", color: "bg-blue-600", description: "Specs and design documents" },
};

// Jira, Notion and Google Docs are implemented end-to-end but each needs its
// own OAuth app, so their cards show as "Coming Soon" until the corresponding
// client ID is configured.
const V1_CONNECTORS = new Set(["github", "linear", "slack"]);

interface ConnectorCardProps {
  connector: ConnectorStatus;
  onToggle?: () => void;
  onConnectedClick?: () => void;
}

export function ConnectorCard({ connector, onToggle, onConnectedClick }: ConnectorCardProps) {
  const meta = connectorMeta[connector.connector] ?? {
    name: connector.connector,
    color: "bg-surface-600",
    description: "External data source",
  };

  const isComingSoon = !V1_CONNECTORS.has(connector.connector);

  const cardProps = onConnectedClick && !isComingSoon
    ? {
        onClick: onConnectedClick,
        role: "button" as const,
        tabIndex: 0,
        onKeyDown: (e: React.KeyboardEvent) => {
          if (e.key === "Enter" || e.key === " ") onConnectedClick();
        },
      }
    : {};

  return (
    <div
      className={cn(
        "card flex flex-col gap-4",
        isComingSoon && "opacity-60",
        onConnectedClick && !isComingSoon && "cursor-pointer transition-shadow hover:shadow-md",
      )}
      {...cardProps}
    >
      <div className="flex items-center gap-3">
        <div
          className={cn(
            "flex h-10 w-10 items-center justify-center rounded-lg text-white text-sm font-bold",
            meta.color,
          )}
        >
          {meta.name.charAt(0)}
        </div>
        <div className="flex-1">
          <h3 className="font-semibold text-surface-900">{meta.name}</h3>
          <p className="text-xs text-surface-500">{meta.description}</p>
        </div>
        {isComingSoon ? (
          <div className="flex items-center gap-1 badge bg-surface-100 text-surface-500">
            <Clock size={12} />
            Coming Soon
          </div>
        ) : (
          <div
            className={cn(
              "flex items-center gap-1 badge",
              connector.connected
                ? "bg-green-100 text-green-700"
                : "bg-surface-100 text-surface-500",
            )}
          >
            {connector.connected ? <Check size={12} /> : <X size={12} />}
            {connector.connected ? "Connected" : "Disconnected"}
          </div>
        )}
      </div>

      {connector.last_sync_at && (
        <div className="flex items-center gap-1.5 text-xs text-surface-400">
          <RefreshCw size={12} />
          Last synced {formatRelativeTime(connector.last_sync_at)}
        </div>
      )}

      {isComingSoon ? (
        <button
          disabled
          className="btn-secondary w-full cursor-not-allowed opacity-50"
        >
          Coming Soon
        </button>
      ) : (
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggle?.();
          }}
          className={cn(
            connector.connected ? "btn-secondary" : "btn-primary",
            "w-full",
          )}
        >
          {connector.connected ? "Disconnect" : "Connect"}
        </button>
      )}
    </div>
  );
}
