import { Link } from "react-router-dom";
import { CheckSquare, ArrowRight } from "lucide-react";
import { useTasks } from "@/hooks/queries";
import { useOrgContext } from "@/contexts/OrgContext";
import { StatusBadge } from "@/components/StatusBadge";
import { PriorityBadge } from "@/components/PriorityBadge";
import type { TaskResponse } from "@/types";

export function MyTasksWidget() {
  const { memberEmail } = useOrgContext();
  const { data: tasks, isPending: loading } = useTasks({ assignee: memberEmail, status: "in_progress" });

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <CheckSquare size={14} className="text-surface-400" />
          <h3 className="text-sm font-semibold text-surface-700">My Active Tasks</h3>
        </div>
        <Link to="/tasks" className="text-xs text-primary-600 hover:text-primary-700 flex items-center gap-1">
          All <ArrowRight size={10} />
        </Link>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse h-8 bg-surface-100 rounded" />
          ))}
        </div>
      ) : tasks && tasks.length > 0 ? (
        <div className="space-y-1.5">
          {tasks.slice(0, 5).map((task: TaskResponse) => (
            <Link
              key={task.id}
              to={`/tasks/${task.id}`}
              className="flex items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-surface-50 transition-colors -mx-2"
            >
              <PriorityBadge priority={task.priority} />
              <span className="flex-1 truncate text-surface-700 font-medium">{task.title}</span>
              <StatusBadge status={task.status} />
            </Link>
          ))}
        </div>
      ) : (
        <p className="text-xs text-surface-400 text-center py-3">No active tasks</p>
      )}
    </div>
  );
}
