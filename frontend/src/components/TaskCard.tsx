import { Link } from "react-router-dom";
import { User, Calendar, FolderKanban } from "lucide-react";
import { StatusBadge } from "@/components/StatusBadge";
import { PriorityBadge } from "@/components/PriorityBadge";
import { InlineEditSelect, InlineEditAssignee } from "@/components/InlineEdit";
import type { TaskResponse, Priority, OrgMember } from "@/types";
import { TaskStatus } from "@/types";
import { STATUS_OPTIONS } from "@/constants/taskStatus";

const sourceConfig: Record<string, { label: string; className: string }> = {
  linear: { label: "LIN", className: "bg-indigo-100 text-indigo-600" },
  github: { label: "GH", className: "bg-gray-100 text-gray-600" },
  manual: { label: "MAN", className: "bg-surface-100 text-surface-500" },
};

const priorityOptions = [
  { value: "urgent", label: "Urgent" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

interface TaskCardProps {
  task: TaskResponse;
  onUpdate?: (taskId: string, updates: Record<string, unknown>) => Promise<void>;
  members?: OrgMember[];
}

export function TaskCard({ task, onUpdate, members = [] }: TaskCardProps) {
  const src = sourceConfig[task.source] ?? sourceConfig["manual"]!;
  const isOverdue = task.due_date && new Date(task.due_date) < new Date() && task.status !== TaskStatus.DONE;

  function stopNav(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
  }

  return (
    <Link to={`/tasks/${task.id}`} className="card block hover:border-primary-200 transition-colors focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-offset-2 focus-visible:outline-none">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          {onUpdate ? (
            <div onClick={stopNav}>
              <InlineEditSelect
                value={task.status}
                options={[...STATUS_OPTIONS]}
                onSave={(v) => onUpdate(task.id, { status: v })}
                renderDisplay={(v) => <StatusBadge status={v} />}
                compact
              />
            </div>
          ) : (
            <StatusBadge status={task.status} />
          )}
          <h3 className="font-medium text-surface-900">{task.title}</h3>
        </div>
        {onUpdate ? (
          <div onClick={stopNav}>
            <InlineEditSelect
              value={task.priority}
              options={priorityOptions}
              onSave={(v) => onUpdate(task.id, { priority: v })}
              renderDisplay={(v) => <PriorityBadge priority={v as Priority} />}
              compact
            />
          </div>
        ) : (
          <PriorityBadge priority={task.priority} />
        )}
      </div>

      <div className="mt-2 flex items-center gap-4 text-xs text-surface-500">
        {onUpdate ? (
          <div onClick={stopNav} className="flex items-center gap-1">
            <User size={12} />
            <InlineEditAssignee
              value={task.assignee ?? null}
              members={members.map((m) => ({ email: m.email, display_name: m.display_name }))}
              onSave={(v) => onUpdate(task.id, { assignee_email: v })}
              compact
            />
          </div>
        ) : (
          <span className="flex items-center gap-1">
            <User size={12} />
            {task.assignee ?? "Unassigned"}
          </span>
        )}

        {task.due_date && (
          <span className={`flex items-center gap-1 ${isOverdue ? "text-red-500" : ""}`}>
            <Calendar size={12} />
            {new Date(task.due_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
          </span>
        )}

        {task.project_id && (
          <span className="flex items-center gap-1">
            <FolderKanban size={12} />
            {task.project_id}
          </span>
        )}

        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${src.className}`}>
          {src.label}
        </span>
      </div>
    </Link>
  );
}
