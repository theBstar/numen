import { cn } from "@/lib/utils";

interface ProgressBarProps {
  value: number;
  label?: string;
  color?: "primary" | "green" | "amber" | "red";
  size?: "sm" | "md";
  className?: string;
}

const colorMap = {
  primary: "bg-primary-600",
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
};

const sizeMap = {
  sm: "h-2",
  md: "h-3",
};

export function ProgressBar({
  value,
  label,
  color = "primary",
  size = "sm",
  className,
}: ProgressBarProps) {
  const clampedValue = Math.min(Math.max(value, 0), 100);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className={cn("flex-1 overflow-hidden rounded-full bg-surface-100", sizeMap[size])}>
        <div
          className={cn("h-full rounded-full transition-all", colorMap[color])}
          style={{ width: `${clampedValue}%` }}
        />
      </div>
      {label && (
        <span className="text-xs font-medium text-surface-500 tabular-nums">
          {label}
        </span>
      )}
    </div>
  );
}
