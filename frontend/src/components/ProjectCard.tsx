import { useNavigate } from "react-router-dom";
import { User, Calendar } from "lucide-react";
import type { ProjectResponse } from "@/types";

const statusColors: Record<ProjectResponse["status"], { bg: string; text: string; dot: string }> = {
  planning: { bg: "bg-blue-50", text: "text-blue-700", dot: "bg-blue-500" },
  active: { bg: "bg-green-50", text: "text-green-700", dot: "bg-green-500" },
  paused: { bg: "bg-yellow-50", text: "text-yellow-700", dot: "bg-yellow-500" },
  completed: { bg: "bg-surface-100", text: "text-surface-600", dot: "bg-surface-400" },
  archived: { bg: "bg-surface-100", text: "text-surface-400", dot: "bg-surface-300" },
};

interface ProjectCardProps {
  project: ProjectResponse;
}

export function ProjectCard({ project }: ProjectCardProps) {
  const navigate = useNavigate();
  const percentage = Math.round(
    (project.tasks_done / Math.max(project.task_count, 1)) * 100,
  );
  const colors = statusColors[project.status];

  return (
    <button
      onClick={() => navigate(`/projects/${project.id}`)}
      className="w-full rounded-xl border border-surface-200 bg-white p-5 text-left shadow-sm hover:shadow-md hover:border-surface-300 transition-all"
    >
      {/* Name */}
      <h3 className="text-base font-semibold text-surface-900 truncate">
        {project.name}
      </h3>

      {/* Status badge */}
      <div className="mt-1.5">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${colors.bg} ${colors.text}`}
        >
          <span className={`h-1.5 w-1.5 rounded-full ${colors.dot}`} />
          {project.status.charAt(0).toUpperCase() + project.status.slice(1)}
        </span>
      </div>

      {/* Progress bar */}
      <div className="mt-4">
        <div className="flex items-center justify-between text-xs text-surface-500">
          <span>Progress</span>
          <span className="font-medium text-surface-700">
            {project.tasks_done}/{project.task_count} ({percentage}%)
          </span>
        </div>
        <div className="mt-1 h-1.5 w-full rounded-full bg-surface-100">
          <div
            className="h-1.5 rounded-full bg-primary-600 transition-all"
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>

      {/* Footer: owner + dates */}
      <div className="mt-4 flex items-center justify-between text-xs text-surface-400">
        <div className="flex items-center gap-1">
          {project.owner ? (
            <>
              <User size={12} />
              <span className="truncate max-w-[120px]">{project.owner}</span>
            </>
          ) : (
            <span>No owner</span>
          )}
        </div>
        {(project.start_date || project.end_date) && (
          <div className="flex items-center gap-1">
            <Calendar size={12} />
            <span>
              {formatShortDate(project.start_date)} - {formatShortDate(project.end_date)}
            </span>
          </div>
        )}
      </div>
    </button>
  );
}

function formatShortDate(dateStr: string | null): string {
  if (!dateStr) return "...";
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
