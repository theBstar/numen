import { cn } from "@/lib/utils";

interface UrgencyBadgeProps {
  score: number;
  className?: string;
}

export function UrgencyBadge({ score, className }: UrgencyBadgeProps) {
  const color =
    score >= 75
      ? "bg-red-100 text-red-800"
      : score >= 50
        ? "bg-orange-100 text-orange-800"
        : score >= 25
          ? "bg-yellow-100 text-yellow-800"
          : "bg-green-100 text-green-800";

  return (
    <span className={cn("badge", color, className)}>
      {score}
    </span>
  );
}
