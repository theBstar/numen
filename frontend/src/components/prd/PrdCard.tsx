import { Calendar, User, Tag } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { PrdStatusBadge } from "@/components/prd/PrdStatusBadge";
import { cn } from "@/lib/utils";
import type { PrdResponse } from "@/types";

const PRIORITY_COLORS: Record<string, string> = {
  urgent: "text-red-600",
  high: "text-orange-600",
  medium: "text-yellow-600",
  low: "text-surface-400",
};

interface PrdCardProps {
  prd: PrdResponse;
  onClick: () => void;
}

export function PrdCard({ prd, onClick }: PrdCardProps) {
  return (
    <Card
      className="cursor-pointer transition-shadow hover:shadow-md"
      onClick={onClick}
    >
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="truncate text-sm font-semibold text-surface-900">
              {prd.title}
            </h3>
            {prd.description && (
              <p className="mt-1 line-clamp-2 text-xs text-surface-500">
                {prd.description}
              </p>
            )}
          </div>
          <PrdStatusBadge status={prd.status} />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-surface-500">
          {prd.priority && (
            <span className={cn("font-medium capitalize", PRIORITY_COLORS[prd.priority] ?? "text-surface-400")}>
              {prd.priority}
            </span>
          )}
          {prd.owner && (
            <span className="flex items-center gap-1">
              <User size={12} />
              {prd.owner}
            </span>
          )}
          {prd.target_date && (
            <span className="flex items-center gap-1">
              <Calendar size={12} />
              {new Date(prd.target_date).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}
            </span>
          )}
          <span className="text-surface-400">
            Updated {new Date(prd.updated_at).toLocaleDateString("en-US", {
              month: "short",
              day: "numeric",
            })}
          </span>
        </div>

        {prd.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {prd.tags.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-0.5 rounded-full bg-surface-100 px-2 py-0.5 text-xs text-surface-600"
              >
                <Tag size={10} />
                {tag}
              </span>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
