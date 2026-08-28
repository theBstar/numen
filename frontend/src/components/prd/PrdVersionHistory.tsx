import { History, GitCommit, ExternalLink } from "lucide-react";
import { PrdStatusBadge } from "@/components/prd/PrdStatusBadge";
import { usePrdVersions } from "@/hooks/prdQueries";
import type { PrdStatus } from "@/types";

interface PrdVersionHistoryProps {
  prdId: string;
  onViewVersion?: (version: number) => void;
}

export function PrdVersionHistory({ prdId, onViewVersion }: PrdVersionHistoryProps) {
  const { data, isLoading } = usePrdVersions(prdId);
  const versions = data?.items ?? [];

  if (isLoading) {
    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-surface-400">
          <History size={14} />
          Version History
        </div>
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 animate-pulse rounded bg-surface-100" />
        ))}
      </div>
    );
  }

  if (versions.length === 0) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-surface-400">
          <History size={14} />
          Version History
        </div>
        <p className="text-xs text-surface-400">
          No versions yet. Save a version to create a snapshot.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold text-surface-400">
        <History size={14} />
        Version History
      </div>

      <div className="space-y-1">
        {versions.map((v) => (
          <button
            key={v.id}
            onClick={() => onViewVersion?.(v.version)}
            className="flex w-full items-start gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors hover:bg-surface-100"
          >
            <GitCommit size={14} className="mt-0.5 shrink-0 text-surface-400" />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium text-surface-900">
                  v{v.version}
                </span>
                <PrdStatusBadge status={v.status_at as PrdStatus} className="text-[10px]" />
              </div>
              {v.message && (
                <p className="mt-0.5 truncate text-xs text-surface-500">
                  {v.message}
                </p>
              )}
              <div className="mt-0.5 flex items-center gap-2 text-xs text-surface-400">
                {v.created_by && <span>{v.created_by}</span>}
                <span>
                  {new Date(v.created_at).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </span>
              </div>
            </div>
            <ExternalLink size={12} className="mt-1 shrink-0 text-surface-300" />
          </button>
        ))}
      </div>
    </div>
  );
}
