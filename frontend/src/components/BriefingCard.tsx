import { useState } from "react";
import { Link } from "react-router-dom";
import * as Separator from "@radix-ui/react-separator";
import { ChevronDown, ChevronUp, ExternalLink, ArrowRight, Zap } from "lucide-react";
import type { BriefingItem } from "@/types";
import { UrgencyBadge } from "./UrgencyBadge";
import { cn } from "@/lib/utils";

interface BriefingCardProps {
  item: BriefingItem;
}

export function BriefingCard({ item }: BriefingCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="card">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-start justify-between gap-3 text-left"
      >
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <UrgencyBadge score={item.urgency_score} />
            <h3 className="font-semibold text-surface-900">
              {item.title}
            </h3>
          </div>
          <p className="mt-1 text-sm text-surface-500 line-clamp-2">
            {item.why_it_matters}
          </p>
        </div>
        <div className="mt-1 shrink-0 text-surface-400">
          {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </div>
      </button>

      {expanded && (
        <div className="mt-4 space-y-3">
          <Separator.Root className="h-px bg-surface-200" />

          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-surface-400">
              Why it matters
            </h4>
            <p className="mt-1 text-sm text-surface-700">
              {item.why_it_matters}
            </p>
          </div>

          {item.goal_tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {item.goal_tags.map((tag) => (
                <span
                  key={tag}
                  className="badge bg-primary-100 text-primary-700"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}

          {item.source_links.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {item.source_links.map((ref, idx) => {
                const isInternal = ref.url.startsWith("/");
                const colorClass = ref.source === "github"
                  ? "bg-gray-100 text-gray-700 hover:bg-gray-200"
                  : ref.source === "linear"
                    ? "bg-violet-100 text-violet-700 hover:bg-violet-200"
                    : ref.source === "numen"
                      ? "bg-primary-100 text-primary-700 hover:bg-primary-200"
                      : "bg-emerald-100 text-emerald-700 hover:bg-emerald-200";
                const classes = cn("inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium transition-colors", colorClass);

                return isInternal ? (
                  <Link key={`${ref.source}-${ref.label}-${idx}`} to={ref.url} className={classes}>
                    {ref.label}
                    <ArrowRight size={12} />
                  </Link>
                ) : (
                  <a key={`${ref.source}-${ref.label}-${idx}`} href={ref.url} target="_blank" rel="noopener noreferrer" className={classes}>
                    {ref.label}
                    <ExternalLink size={12} />
                  </a>
                );
              })}
            </div>
          )}

          <Separator.Root className="h-px bg-surface-200" />

          {item.suggested_action && (
            <div className="flex items-start gap-2 rounded-lg bg-primary-50 p-3">
              <Zap size={16} className="mt-0.5 shrink-0 text-primary-600" />
              <div>
                <h4 className="text-xs font-semibold uppercase tracking-wider text-primary-600">
                  Suggested action
                </h4>
                <p className="mt-0.5 text-sm text-primary-800">
                  {item.suggested_action}
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
