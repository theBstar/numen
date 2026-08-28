import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import type { SourceDot } from "@/types/livingPrd";

const dotVariants = cva("inline-block rounded-full ring-1 ring-white", {
  variants: {
    type: {
      notion: "bg-slate-700",
      gdocs: "bg-amber-500",
      git: "bg-rose-500",
      slack: "bg-violet-500",
    },
    size: {
      sm: "h-2 w-2",
      md: "h-2.5 w-2.5",
    },
  },
  defaultVariants: { size: "sm" },
});

export type SourceDotVariantProps = VariantProps<typeof dotVariants>;

export interface SourceDotStackProps {
  sources: SourceDot[];
  className?: string;
  size?: SourceDotVariantProps["size"];
}

/**
 * Renders a horizontal stack of color-coded dots, one per source the
 * synthesizer pulled from for a section. Sorted by descending weight so the
 * most-weighted source is visible first.
 */
export function SourceDotStack({ sources, className, size }: SourceDotStackProps) {
  if (sources.length === 0) {
    return (
      <span
        className={cn("text-[10px] uppercase tracking-wide text-muted-foreground", className)}
        data-testid="source-stack-empty"
      >
        no sources
      </span>
    );
  }

  const sorted = [...sources].sort((a, b) => b.weight - a.weight);

  return (
    <span
      className={cn("inline-flex items-center gap-0.5", className)}
      data-testid="source-stack"
      aria-label={`Sources: ${sorted.map((s) => s.type).join(", ")}`}
    >
      {sorted.map((s, idx) => (
        <span
          key={`${s.type}-${idx}`}
          data-testid={`source-dot-${s.type}`}
          className={cn(dotVariants({ type: s.type, size }))}
          title={`${s.type} (weight ${s.weight.toFixed(2)})`}
        />
      ))}
    </span>
  );
}
