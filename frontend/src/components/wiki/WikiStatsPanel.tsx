import { Layers, CheckCircle2, Clock, Tag, Sparkles } from "lucide-react";
import type { WikiStats } from "@/types";

interface WikiStatsPanelProps {
  stats: WikiStats;
}

export function WikiStatsPanel({ stats }: WikiStatsPanelProps) {
  const items = [
    {
      label: "Total Features",
      value: stats.total_features,
      icon: Layers,
      color: "text-surface-600",
      bg: "bg-surface-100",
    },
    {
      label: "Active",
      value: stats.active,
      icon: CheckCircle2,
      color: "text-green-600",
      bg: "bg-green-50",
    },
    {
      label: "Planned",
      value: stats.planned,
      icon: Clock,
      color: "text-amber-600",
      bg: "bg-amber-50",
    },
    {
      label: "Manual Edits",
      value: stats.manual_edits,
      icon: Tag,
      color: "text-blue-600",
      bg: "bg-blue-50",
    },
    {
      label: "Concepts",
      value: stats.concept_count,
      icon: Sparkles,
      color: "text-orange-600",
      bg: "bg-orange-50",
    },
  ];

  return (
    <div className="border-t border-surface-200 px-3 py-3">
      <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-surface-400">
        Stats
      </p>
      <div className="space-y-1.5">
        {items.map((item) => (
          <div
            key={item.label}
            className="flex items-center gap-2 rounded-md px-2 py-1.5 text-xs"
          >
            <div className={`flex h-6 w-6 shrink-0 items-center justify-center rounded ${item.bg}`}>
              <item.icon size={12} className={item.color} />
            </div>
            <span className="flex-1 text-surface-600">{item.label}</span>
            <span className="font-semibold text-surface-800">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
