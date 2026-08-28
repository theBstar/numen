import { formatRelativeTime } from "@/lib/utils";
import type { AgentRead } from "@/types/livingPrd";

export interface AgentReadIndicatorProps {
  reads: AgentRead[];
}

/**
 * Renders the most recent agent read as "Read by #task_id · Xs ago". Hidden
 * entirely when no agent has read the section recently (empty reads array).
 */
export function AgentReadIndicator({ reads }: AgentReadIndicatorProps) {
  if (reads.length === 0) return null;
  // Most recent first by timestamp
  const sorted = [...reads].sort(
    (a, b) => new Date(b.when).getTime() - new Date(a.when).getTime(),
  );
  const latest = sorted[0];
  if (!latest) return null;

  return (
    <span
      data-testid="agent-read"
      className="inline-flex items-center gap-1 text-[11px] text-blue-600"
    >
      <span
        aria-hidden="true"
        className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-blue-500"
      />
      Read by #{latest.taskId} · {formatRelativeTime(latest.when)}
      {sorted.length > 1 ? ` (+${sorted.length - 1})` : ""}
    </span>
  );
}
