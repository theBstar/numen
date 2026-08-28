import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { usePrdAlignmentChecks } from "@/hooks/prdQueries";
import { useAcknowledgeFinding, useResolveFinding } from "@/hooks/prdMutations";
import type { AlignmentCheckResponse, AlignmentFinding, AlignmentSeverity } from "@/types";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Eye,
  FileWarning,
  Shield,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

interface PrdAlignmentPanelProps {
  prdId: string;
}

const SEVERITY_CONFIG: Record<
  AlignmentSeverity,
  { color: string; bgColor: string; borderColor: string; label: string }
> = {
  high: {
    color: "text-red-700",
    bgColor: "bg-red-50",
    borderColor: "border-red-200",
    label: "High",
  },
  medium: {
    color: "text-orange-700",
    bgColor: "bg-orange-50",
    borderColor: "border-orange-200",
    label: "Medium",
  },
  low: {
    color: "text-yellow-700",
    bgColor: "bg-yellow-50",
    borderColor: "border-yellow-200",
    label: "Low",
  },
};

const FINDING_TYPE_LABELS: Record<string, string> = {
  missing_requirement: "Missing Requirement",
  label_mismatch: "Label Mismatch",
  assumption_conflict: "Assumption Conflict",
  scope_drift: "Scope Drift",
};

function CoverageBar({ score }: { score: number | null }) {
  if (score === null || score === undefined) return null;
  const pct = Math.round(score * 100);
  const color =
    pct >= 80
      ? "bg-emerald-500"
      : pct >= 50
        ? "bg-orange-500"
        : "bg-red-500";

  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 flex-1 rounded-full bg-surface-100">
        <div
          className={cn("h-1.5 rounded-full transition-all", color)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-medium text-surface-500">{pct}%</span>
    </div>
  );
}

function FindingItem({ finding }: { finding: AlignmentFinding }) {
  const severity = SEVERITY_CONFIG[finding.severity] ?? SEVERITY_CONFIG.low;

  return (
    <div
      className={cn(
        "rounded-md border p-2.5",
        severity.borderColor,
        severity.bgColor,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5">
            <span
              className={cn(
                "inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase",
                severity.color,
                severity.bgColor,
              )}
            >
              {severity.label}
            </span>
            <span className="text-xs font-medium text-surface-500">
              {FINDING_TYPE_LABELS[finding.type] ?? finding.type}
            </span>
          </div>
          {finding.prd_section && (
            <p className="mt-1 text-xs text-surface-400">
              Section: {finding.prd_section}
            </p>
          )}
          <p className="mt-1 text-sm text-surface-700">{finding.detail}</p>
        </div>
      </div>
    </div>
  );
}

function AlignmentCheckCard({
  check,
  prdId,
}: {
  check: AlignmentCheckResponse;
  prdId: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const acknowledgeMutation = useAcknowledgeFinding(prdId);
  const resolveMutation = useResolveFinding(prdId);

  const findingCount = check.findings?.length ?? 0;
  const isResolved = check.status === "resolved";
  const isAcknowledged = check.status === "acknowledged";

  const StatusIcon = isResolved
    ? ShieldCheck
    : isAcknowledged
      ? Shield
      : ShieldAlert;
  const statusColor = isResolved
    ? "text-emerald-600"
    : isAcknowledged
      ? "text-blue-600"
      : "text-surface-500";

  return (
    <div className="rounded-lg border border-surface-200 bg-white">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-surface-50"
      >
        {expanded ? (
          <ChevronDown className="h-4 w-4 flex-shrink-0 text-surface-400" />
        ) : (
          <ChevronRight className="h-4 w-4 flex-shrink-0 text-surface-400" />
        )}
        <StatusIcon className={cn("h-4 w-4 flex-shrink-0", statusColor)} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-surface-700">
            {check.pr_title ?? "Unknown PR"}
          </p>
          <div className="mt-0.5 flex items-center gap-3">
            <CoverageBar score={check.coverage_score} />
            {findingCount > 0 && (
              <span className="whitespace-nowrap text-xs text-surface-400">
                {findingCount} finding{findingCount !== 1 ? "s" : ""}
              </span>
            )}
          </div>
        </div>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-medium",
            isResolved
              ? "bg-emerald-100 text-emerald-700"
              : isAcknowledged
                ? "bg-blue-100 text-blue-700"
                : "bg-surface-100 text-surface-500",
          )}
        >
          {check.status}
        </span>
      </button>

      {expanded && (
        <div className="border-t border-surface-100 px-3 py-3">
          {findingCount === 0 ? (
            <p className="text-sm text-surface-400">
              No issues found - PR fully covers PRD requirements.
            </p>
          ) : (
            <div className="space-y-2">
              {check.findings.map((finding, idx) => (
                <FindingItem key={idx} finding={finding} />
              ))}
            </div>
          )}

          {/* Actions */}
          {check.status === "pending" && (
            <div className="mt-3 flex gap-2">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={(e) => {
                  e.stopPropagation();
                  acknowledgeMutation.mutate(check.id);
                }}
                disabled={acknowledgeMutation.isPending}
              >
                <Eye className="h-3.5 w-3.5" />
                Acknowledge
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={(e) => {
                  e.stopPropagation();
                  resolveMutation.mutate(check.id);
                }}
                disabled={resolveMutation.isPending}
              >
                <Check className="h-3.5 w-3.5" />
                Resolve
              </Button>
            </div>
          )}
          {check.status === "acknowledged" && (
            <div className="mt-3">
              <Button
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={(e) => {
                  e.stopPropagation();
                  resolveMutation.mutate(check.id);
                }}
                disabled={resolveMutation.isPending}
              >
                <Check className="h-3.5 w-3.5" />
                Resolve
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function PrdAlignmentPanel({ prdId }: PrdAlignmentPanelProps) {
  const { data, isLoading } = usePrdAlignmentChecks(prdId);
  const checks = data?.items ?? [];

  if (isLoading) {
    return (
      <div className="space-y-2">
        <div className="h-4 w-32 animate-pulse rounded bg-surface-100" />
        <div className="h-16 animate-pulse rounded-lg bg-surface-50" />
      </div>
    );
  }

  // Summary stats
  const pendingCount = checks.filter((c) => c.status === "pending").length;
  const totalFindings = checks.reduce(
    (sum, c) => sum + (c.findings?.length ?? 0),
    0,
  );

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileWarning className="h-4 w-4 text-surface-500" />
          <span className="text-xs font-medium text-surface-500">
            PR Alignment
          </span>
        </div>
        {pendingCount > 0 && (
          <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700">
            {pendingCount} pending
          </span>
        )}
      </div>

      {/* Summary */}
      {checks.length > 0 && totalFindings > 0 && (
        <div className="rounded-md bg-surface-50 p-2.5">
          <div className="flex items-center justify-between">
            <span className="text-xs text-surface-400">
              {checks.length} check{checks.length !== 1 ? "s" : ""} -
              {" "}{totalFindings} finding{totalFindings !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
      )}

      {/* Check list */}
      {checks.length === 0 ? (
        <div className="rounded-lg border border-dashed border-surface-200 p-4 text-center">
          <AlertTriangle className="mx-auto h-5 w-5 text-surface-300" />
          <p className="mt-1.5 text-sm text-surface-400">
            No alignment checks yet
          </p>
          <p className="mt-0.5 text-xs text-surface-300">
            Checks run automatically when PRs linked to this PRD are synced
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {checks.map((check) => (
            <AlignmentCheckCard
              key={check.id}
              check={check}
              prdId={prdId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
