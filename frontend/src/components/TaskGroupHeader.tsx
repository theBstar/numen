import { ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface TaskGroupHeaderProps {
  label: string;
  count: number;
  isExpanded: boolean;
  onToggle: () => void;
  badge?: React.ReactNode;
}

export function TaskGroupHeader({
  label,
  count,
  isExpanded,
  onToggle,
  badge,
}: TaskGroupHeaderProps) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left transition-colors",
        "hover:bg-surface-50",
      )}
    >
      {isExpanded ? (
        <ChevronDown size={16} className="text-surface-400" />
      ) : (
        <ChevronRight size={16} className="text-surface-400" />
      )}
      <span className="text-sm font-semibold text-surface-700">{label}</span>
      {badge}
      <span className="rounded-full bg-surface-100 px-2 py-0.5 text-xs font-medium text-surface-500">
        {count}
      </span>
    </button>
  );
}
