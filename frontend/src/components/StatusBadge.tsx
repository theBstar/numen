import { STATUS_CONFIG } from "@/constants/taskStatus";

const fallback = { label: "Unknown", className: "bg-gray-100 text-gray-500" };

export function StatusBadge({ status }: { status: string }) {
  const normalized = status?.toLowerCase().replace(/\s+/g, "_") ?? "todo";
  const config = STATUS_CONFIG[normalized] ?? fallback;
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${config.className}`}>
      {config.label}
    </span>
  );
}
