import type { Entity } from "@/types";
import { cn, formatRelativeTime } from "@/lib/utils";
import { entityTypeConfig } from "@/constants/entityConfig";

const sourceColors: Record<string, string> = {
  linear: "bg-violet-100 text-violet-700",
  github: "bg-gray-100 text-gray-700",
  slack: "bg-emerald-100 text-emerald-700",
  manual: "bg-surface-100 text-surface-600",
};

interface EntityCardProps {
  entity: Entity;
}

export function EntityCard({ entity }: EntityCardProps) {
  const config = entityTypeConfig[entity.type] ?? entityTypeConfig.task;
  const Icon = config.icon;

  return (
    <div className="card flex items-center gap-4">
      <div className={cn("flex h-10 w-10 items-center justify-center rounded-lg", config.bg)}>
        <Icon size={20} className={config.color} />
      </div>
      <div className="flex-1 min-w-0">
        <h3 className="font-medium text-surface-900 truncate">
          {entity.canonical_name}
        </h3>
        <div className="mt-1 flex items-center gap-2">
          <span className={cn("badge", sourceColors[entity.source] ?? sourceColors.manual)}>
            {entity.source}
          </span>
          <span className="text-xs text-surface-400">
            {formatRelativeTime(entity.updated_at)}
          </span>
        </div>
      </div>
    </div>
  );
}
