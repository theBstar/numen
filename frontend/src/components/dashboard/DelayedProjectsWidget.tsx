import { Link } from "react-router-dom";
import { Clock, ArrowRight } from "lucide-react";
import type { DelayedProject } from "@/types";

interface DelayedProjectsWidgetProps {
  projects: DelayedProject[];
}

export function DelayedProjectsWidget({ projects }: DelayedProjectsWidgetProps) {
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Clock size={14} className="text-surface-400" />
          <h3 className="text-sm font-semibold text-surface-700">Delayed Projects</h3>
        </div>
        <Link to="/projects" className="text-xs text-primary-600 hover:text-primary-700 flex items-center gap-1">
          All <ArrowRight size={10} />
        </Link>
      </div>

      {projects.length > 0 ? (
        <div className="space-y-2">
          {projects.slice(0, 5).map((p) => (
            <Link
              key={p.id}
              to={`/projects/${p.id}`}
              className="flex items-center justify-between rounded-lg px-2 py-2 text-xs hover:bg-surface-50 transition-colors -mx-2"
            >
              <div className="flex-1 min-w-0">
                <p className="font-medium text-surface-700 truncate">{p.name}</p>
                <p className="text-surface-400">
                  {p.remaining_tasks} task{p.remaining_tasks !== 1 ? "s" : ""} remaining
                </p>
              </div>
              <span className="shrink-0 ml-2 rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-medium text-red-700">
                {p.days_overdue}d overdue
              </span>
            </Link>
          ))}
        </div>
      ) : (
        <p className="text-xs text-green-600 text-center py-3">All projects on track</p>
      )}
    </div>
  );
}
