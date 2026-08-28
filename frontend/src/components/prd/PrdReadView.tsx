import { Loader2 } from "lucide-react";
import { usePrd, usePrdBlocks } from "@/hooks/prdQueries";
import { PrdEditor } from "./PrdEditor";
import { PrdStatusBadge } from "./PrdStatusBadge";
import type { PrdStatus } from "@/types";

interface PrdReadViewProps {
  prdId: string;
}

export function PrdReadView({ prdId }: PrdReadViewProps) {
  const { data: prd, isLoading: prdLoading } = usePrd(prdId);
  const { data: blocksData, isLoading: blocksLoading } = usePrdBlocks(prdId);

  const blocks = blocksData?.items ?? [];

  if (prdLoading) {
    return (
      <div className="flex items-center justify-center py-16 text-surface-400">
        <Loader2 size={16} className="animate-spin mr-2" />
        <span className="text-sm">Loading...</span>
      </div>
    );
  }

  if (!prd) {
    return (
      <div className="flex items-center justify-center py-16 text-surface-400">
        <span className="text-sm">PRD not found.</span>
      </div>
    );
  }

  return (
    <div className="px-8 py-6 max-w-4xl mx-auto">
      {/* Title */}
      <h1 className="text-3xl font-bold text-surface-900">{prd.title}</h1>

      {/* Metadata row */}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <PrdStatusBadge status={prd.status as PrdStatus} />
        {prd.priority && (
          <span className="rounded-full bg-surface-100 px-2 py-0.5 text-xs text-surface-600">
            {prd.priority}
          </span>
        )}
        {prd.tags?.map((tag) => (
          <span
            key={tag}
            className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700"
          >
            {tag}
          </span>
        ))}
      </div>

      {prd.description && (
        <p className="mt-3 text-sm text-surface-500">{prd.description}</p>
      )}

      {/* Content */}
      <div className="mt-8">
        {blocksLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-6 animate-pulse rounded bg-surface-100"
                style={{ width: `${60 + Math.random() * 30}%` }}
              />
            ))}
          </div>
        ) : (
          <PrdEditor
            blocks={blocks}
            onSave={() => {}}
            readOnly={true}
            entityId={prdId}
          />
        )}
      </div>
    </div>
  );
}
