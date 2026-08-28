import ReactMarkdown from "react-markdown";
import { cn } from "@/lib/utils";
import { SourceDotStack } from "./SourceDotStack";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { AgentReadIndicator } from "./AgentReadIndicator";
import { ConflictPill } from "./ConflictPill";
import type { LivingPrdSection } from "@/types/livingPrd";

export interface LivingPrdSectionCardProps {
  section: LivingPrdSection;
  selected: boolean;
  onSelect: () => void;
  onOpenConflict: () => void;
}

/**
 * One synthesized PRD section. Hover/selected states drive the right pane
 * provenance content. The conflict pill is a separate clickable surface so
 * users can jump straight to the resolution card without selecting first.
 */
export function LivingPrdSectionCard({
  section,
  selected,
  onSelect,
  onOpenConflict,
}: LivingPrdSectionCardProps) {
  const hasConflict = !!section.conflict;
  return (
    <article
      data-testid={`section-${section.id}`}
      data-selected={selected ? "true" : undefined}
      data-has-conflict={hasConflict ? "true" : undefined}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      className={cn(
        "group cursor-pointer rounded-md border-l-2 border-transparent px-4 py-3 transition-colors",
        "hover:bg-slate-50",
        selected && "border-emerald-400 bg-slate-50",
        hasConflict && "border-rose-400",
      )}
    >
      <header className="mb-2 flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold tracking-tight text-foreground">
          {section.title}
        </h3>
        <div className="flex flex-shrink-0 items-center gap-2">
          <SourceDotStack sources={section.sources} />
          <ConfidenceBadge value={section.confidence} />
          {hasConflict && section.conflict ? (
            <ConflictPill
              sourceCount={section.conflict.sources.length}
              onClick={(): void => {
                onOpenConflict();
              }}
            />
          ) : null}
        </div>
      </header>
      <div className="prose prose-sm max-w-none text-sm text-slate-700">
        <ReactMarkdown>{section.body}</ReactMarkdown>
      </div>
      {section.recentAgentReads.length > 0 ? (
        <footer className="mt-2">
          <AgentReadIndicator reads={section.recentAgentReads} />
        </footer>
      ) : null}
    </article>
  );
}
