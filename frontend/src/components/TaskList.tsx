import { useState } from "react";
import type { TaskResponse } from "@/types";
import { STATUS_OPTIONS } from "@/constants/taskStatus";

interface TaskListProps {
  tasks: TaskResponse[];
  onStatusChange?: (taskId: string, newStatus: string) => void;
}

type SortKey = "title" | "status" | "priority" | "assignee" | "due_date";
type SortDir = "asc" | "desc";

const columnDefs: { key: SortKey; label: string }[] = [
  { key: "title", label: "Title" },
  { key: "status", label: "Status" },
  { key: "priority", label: "Priority" },
  { key: "assignee", label: "Assignee" },
  { key: "due_date", label: "Due Date" },
];

const priorityOrder: Record<string, number> = { urgent: 0, high: 1, medium: 2, low: 3 };

export function TaskList({ tasks, onStatusChange }: TaskListProps) {
  const [sortKey, setSortKey] = useState<SortKey>("title");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sorted = [...tasks].sort((a, b) => {
    let cmp = 0;
    switch (sortKey) {
      case "title":
        cmp = (a.title || "").localeCompare(b.title || "");
        break;
      case "status":
        cmp = (a.status || "").localeCompare(b.status || "");
        break;
      case "priority":
        cmp = (priorityOrder[a.priority] ?? 2) - (priorityOrder[b.priority] ?? 2);
        break;
      case "assignee":
        cmp = (a.assignee || "").localeCompare(b.assignee || "");
        break;
      case "due_date":
        cmp = (a.due_date || "9999").localeCompare(b.due_date || "9999");
        break;
    }
    return sortDir === "asc" ? cmp : -cmp;
  });

  return (
    <div className="overflow-hidden rounded-lg border border-surface-200">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-surface-200 bg-surface-50">
            {columnDefs.map((col) => (
              <th
                key={col.key}
                onClick={() => toggleSort(col.key)}
                className="cursor-pointer px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-surface-500 hover:text-surface-700"
              >
                <div className="flex items-center gap-1">
                  {col.label}
                  {sortKey === col.key && (
                    <span>{sortDir === "asc" ? "\u2191" : "\u2193"}</span>
                  )}
                </div>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-100">
          {sorted.map((task) => (
            <tr key={task.id} className="hover:bg-surface-50 transition-colors">
              <td className="px-4 py-3 font-medium text-surface-900 truncate max-w-xs">
                {task.title}
              </td>
              <td className="px-4 py-3">
                {onStatusChange ? (
                  <select
                    value={task.status}
                    onChange={(e) => onStatusChange(task.id, e.target.value)}
                    className="rounded border border-surface-200 px-2 py-1 text-xs text-surface-600 focus:border-primary-300 focus:outline-none"
                  >
                    {STATUS_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                ) : (
                  <StatusDot status={task.status} />
                )}
              </td>
              <td className="px-4 py-3">
                <PriorityBadge priority={task.priority} />
              </td>
              <td className="px-4 py-3 text-surface-500 truncate max-w-[140px]">
                {task.assignee || "Unassigned"}
              </td>
              <td className="px-4 py-3 text-surface-500">
                {task.due_date ? formatShortDate(task.due_date) : "--"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {sorted.length === 0 && (
        <div className="py-8 text-center text-sm text-surface-400">
          No tasks in this project yet.
        </div>
      )}
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    todo: "bg-surface-400",
    in_progress: "bg-blue-500",
    in_review: "bg-yellow-500",
    done: "bg-green-500",
  };
  const labels: Record<string, string> = {
    todo: "To Do",
    in_progress: "In Progress",
    in_review: "In Review",
    done: "Done",
  };
  return (
    <span className="flex items-center gap-1.5 text-xs text-surface-600">
      <span className={`h-2 w-2 rounded-full ${colors[status]}`} />
      {labels[status]}
    </span>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    urgent: "bg-red-50 text-red-700",
    high: "bg-orange-50 text-orange-700",
    medium: "bg-blue-50 text-blue-700",
    low: "bg-surface-100 text-surface-600",
  };
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${colors[priority] || colors.medium}`}
    >
      {priority.charAt(0).toUpperCase() + priority.slice(1)}
    </span>
  );
}

function formatShortDate(dateStr: string | null): string {
  if (!dateStr) return "...";
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
