import { cn } from "@/lib/utils";
import type { PrdStatus } from "@/types";

const STATUS_CONFIG: Record<PrdStatus, { label: string; className: string }> = {
  idea: { label: "Idea", className: "bg-gray-100 text-gray-700" },
  draft: { label: "Draft", className: "bg-yellow-100 text-yellow-700" },
  in_review: { label: "In Review", className: "bg-blue-100 text-blue-700" },
  needs_revision: { label: "Needs Revision", className: "bg-orange-100 text-orange-700" },
  approved: { label: "Approved", className: "bg-green-100 text-green-700" },
  in_progress: { label: "In Progress", className: "bg-indigo-100 text-indigo-700" },
  shipped: { label: "Shipped", className: "bg-emerald-100 text-emerald-700" },
  deprecated: { label: "Deprecated", className: "bg-red-100 text-red-700" },
  archived: { label: "Archived", className: "bg-gray-100 text-gray-500" },
};

interface PrdStatusBadgeProps {
  status: PrdStatus;
  className?: string;
}

export function PrdStatusBadge({ status, className }: PrdStatusBadgeProps) {
  const config = STATUS_CONFIG[status] ?? { label: status, className: "bg-gray-100 text-gray-600" };
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  );
}

export function getStatusDotColor(status: PrdStatus): string {
  const map: Record<PrdStatus, string> = {
    idea: "bg-gray-400",
    draft: "bg-yellow-400",
    in_review: "bg-blue-400",
    needs_revision: "bg-orange-400",
    approved: "bg-green-400",
    in_progress: "bg-indigo-400",
    shipped: "bg-emerald-400",
    deprecated: "bg-red-400",
    archived: "bg-gray-300",
  };
  return map[status] ?? "bg-gray-400";
}
