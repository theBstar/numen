import type { Priority } from "@/types";

const priorityConfig: Record<string, { label: string; className: string }> = {
  urgent: { label: "Urgent", className: "bg-red-100 text-red-700" },
  high:   { label: "High",   className: "bg-orange-100 text-orange-700" },
  medium: { label: "Medium", className: "bg-yellow-100 text-yellow-700" },
  low:    { label: "Low",    className: "bg-gray-100 text-gray-500" },
  none:   { label: "No priority", className: "bg-surface-100 text-surface-500" },
};

const fallback = { label: "Unknown", className: "bg-surface-100 text-surface-500" };

export function PriorityBadge({ priority }: { priority: Priority | string | null | undefined }) {
  const key = (priority ?? "none").toLowerCase();
  const config = priorityConfig[key] ?? fallback;
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${config.className}`}>
      {config.label}
    </span>
  );
}
