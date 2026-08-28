import { AlertTriangle } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ConflictPillProps {
  sourceCount: number;
  onClick?: () => void;
  className?: string;
}

/**
 * Red conflict pill shown next to a section's title when its sources
 * disagree. Clicking opens the resolution card in the right pane.
 */
export function ConflictPill({ sourceCount, onClick, className }: ConflictPillProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="conflict-pill"
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-rose-200 bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700 transition-colors hover:bg-rose-100 focus:outline-none focus:ring-2 focus:ring-rose-300",
        className,
      )}
    >
      <AlertTriangle className="h-3 w-3" aria-hidden="true" />
      Conflict · {sourceCount} sources
    </button>
  );
}
