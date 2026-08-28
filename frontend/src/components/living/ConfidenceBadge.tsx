import { cn } from "@/lib/utils";

export interface ConfidenceBadgeProps {
  /** 0-1 score from the synthesizer. */
  value: number;
  className?: string;
}

/**
 * Numeric confidence badge for a Living PRD section. Color bucket maps to
 * the design doc thresholds: high (>=0.8) green, medium (>=0.5) amber,
 * low otherwise red.
 */
export function ConfidenceBadge({ value, className }: ConfidenceBadgeProps) {
  const clamped = Math.max(0, Math.min(1, value));
  const tone =
    clamped >= 0.8
      ? "text-emerald-700 bg-emerald-50 border-emerald-200"
      : clamped >= 0.5
        ? "text-amber-700 bg-amber-50 border-amber-200"
        : "text-rose-700 bg-rose-50 border-rose-200";

  return (
    <span
      data-testid="confidence-badge"
      className={cn(
        "inline-flex items-center rounded border px-1.5 py-px font-mono text-[11px] tabular-nums",
        tone,
        className,
      )}
    >
      {clamped.toFixed(2)}
    </span>
  );
}
