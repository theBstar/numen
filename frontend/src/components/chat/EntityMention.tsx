import { Link } from "react-router-dom";
import type { EntityType } from "@/types";
import { cn } from "@/lib/utils";
import { entityTypeConfig, getEntityRoute } from "@/constants/entityConfig";

interface EntityMentionProps {
  type: EntityType;
  name: string;
  id: string;
}

export function EntityMention({ type, name, id }: EntityMentionProps) {
  const config = entityTypeConfig[type] ?? entityTypeConfig.task;
  const Icon = config.icon;
  const route = getEntityRoute(type, id);

  return (
    <Link
      to={route}
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium transition-colors hover:opacity-80",
        config.bg,
        config.color,
      )}
    >
      <Icon size={12} />
      <span className="max-w-[200px] truncate">{name}</span>
    </Link>
  );
}
