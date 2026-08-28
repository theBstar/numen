import { useNavigate } from "react-router-dom";
import { Target } from "lucide-react";
import { cn } from "@/lib/utils";
import { ProgressBar } from "./ProgressBar";
import type { GoalResponse } from "@/types";

interface GoalCardProps {
  goal: GoalResponse;
  className?: string;
}

const levelColors: Record<string, string> = {
  company: "bg-purple-100 text-purple-700",
  team: "bg-blue-100 text-blue-700",
  individual: "bg-emerald-100 text-emerald-700",
};

export function GoalCard({ goal, className }: GoalCardProps) {
  const navigate = useNavigate();

  const progress = goal.computed_progress
    ?? (goal.target_value && goal.target_value > 0
      ? Math.round(((goal.current_value ?? 0) / goal.target_value) * 100)
      : 0);

  return (
    <button
      onClick={() => navigate(`/goals/${goal.id}`)}
      className={cn(
        "card w-full text-left transition-shadow hover:shadow-md",
        className
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 flex h-9 w-9 items-center justify-center rounded-lg bg-amber-100">
            <Target size={18} className="text-amber-600" />
          </div>
          <div>
            <h3 className="font-semibold text-surface-900">{goal.title}</h3>
            <div className="mt-1 flex items-center gap-3 text-xs text-surface-500">
              {goal.owner && <span>Owner: {goal.owner}</span>}
              {goal.key_results.length > 0 && (
                <span>{goal.key_results.length} key result{goal.key_results.length !== 1 ? "s" : ""}</span>
              )}
              {goal.time_bound_end && (
                <span>Due: {new Date(goal.time_bound_end).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}</span>
              )}
            </div>
          </div>
        </div>
        <span className={cn("badge", levelColors[goal.level] ?? "bg-surface-100 text-surface-600")}>
          {goal.level}
        </span>
      </div>
      <div className="mt-3">
        <ProgressBar value={progress} label={`${progress}%`} />
      </div>
    </button>
  );
}
