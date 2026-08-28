import { Link } from "react-router-dom";
import { Target, ArrowRight } from "lucide-react";
import { useGoals } from "@/hooks/queries";
import type { GoalResponse } from "@/types";

export function GoalProgressWidget() {
  const { data: goals, isPending: loading } = useGoals();

  const activeGoals = (goals ?? []).filter((g: GoalResponse) => g.status === "active");

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Target size={14} className="text-surface-400" />
          <h3 className="text-sm font-semibold text-surface-700">Goal Progress</h3>
        </div>
        <Link to="/goals" className="text-xs text-primary-600 hover:text-primary-700 flex items-center gap-1">
          All <ArrowRight size={10} />
        </Link>
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse h-10 bg-surface-100 rounded" />
          ))}
        </div>
      ) : activeGoals.length > 0 ? (
        <div className="space-y-3">
          {activeGoals.slice(0, 4).map((goal: GoalResponse) => {
            const progress = goal.computed_progress ?? 0;
            return (
              <Link key={goal.id} to={`/goals/${goal.id}`} className="block group">
                <div className="flex items-center justify-between text-xs mb-1">
                  <span className="font-medium text-surface-700 truncate group-hover:text-primary-600 transition-colors">
                    {goal.title}
                  </span>
                  <span className="text-surface-500 shrink-0 ml-2">{Math.round(progress)}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-surface-100 overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all bg-primary-500"
                    style={{ width: `${Math.min(progress, 100)}%` }}
                  />
                </div>
              </Link>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-surface-400 text-center py-3">No active goals</p>
      )}
    </div>
  );
}
