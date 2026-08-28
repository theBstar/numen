import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface MetricCardProps {
  label: string;
  value: number;
  icon: LucideIcon;
  color?: "default" | "red" | "amber" | "green" | "blue";
  href?: string;
}

const colorStyles = {
  default: "bg-surface-50 text-surface-600",
  red: "bg-red-50 text-red-600",
  amber: "bg-amber-50 text-amber-600",
  green: "bg-green-50 text-green-600",
  blue: "bg-blue-50 text-blue-600",
} as const;

export function MetricCard({ label, value, icon: Icon, color = "default", href }: MetricCardProps) {
  const content = (
    <div className={cn(
      "card flex items-center gap-3 transition-colors",
      href && "hover:border-primary-300 cursor-pointer",
    )}>
      <div className={cn("rounded-lg p-2", colorStyles[color])}>
        <Icon size={18} />
      </div>
      <div>
        <p className="text-2xl font-bold text-surface-900">{value}</p>
        <p className="text-xs text-surface-500">{label}</p>
      </div>
    </div>
  );

  if (href) {
    return <a href={href}>{content}</a>;
  }

  return content;
}
