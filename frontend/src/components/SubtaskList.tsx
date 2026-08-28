import { useState } from "react";
import { Link } from "react-router-dom";
import { Plus, CheckCircle2, Circle, Loader2 } from "lucide-react";
import { useSubtasks } from "@/hooks/queries";
import { useCreateSubtask, useUpdateTask } from "@/hooks/mutations";
import { TaskStatus } from "@/types";
import { PriorityBadge } from "@/components/PriorityBadge";
import type { Priority } from "@/types";

interface SubtaskListProps {
  taskId: string;
}

export function SubtaskList({ taskId }: SubtaskListProps) {
  const { data, isLoading } = useSubtasks(taskId);
  const createSubtask = useCreateSubtask();
  const updateTask = useUpdateTask();
  const [showAdd, setShowAdd] = useState(false);
  const [newTitle, setNewTitle] = useState("");

  const subtasks = data?.items ?? [];
  const doneCount = subtasks.filter(
    (t) => t.status === TaskStatus.DONE || t.status === TaskStatus.MERGED,
  ).length;
  const progress = subtasks.length > 0 ? (doneCount / subtasks.length) * 100 : 0;

  async function handleAddSubtask() {
    const title = newTitle.trim();
    if (!title) return;
    await createSubtask.mutateAsync({
      taskId,
      data: { title },
    });
    setNewTitle("");
  }

  function toggleSubtask(subtaskId: string, currentStatus: string) {
    const newStatus =
      currentStatus === TaskStatus.DONE ? TaskStatus.TODO : TaskStatus.DONE;
    updateTask.mutate({ id: subtaskId, data: { status: newStatus } });
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-surface-700">
          Subtasks
          {subtasks.length > 0 && (
            <span className="ml-2 text-xs font-normal text-surface-400">
              {doneCount}/{subtasks.length}
            </span>
          )}
        </h3>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-surface-500 hover:bg-surface-100 hover:text-surface-700"
        >
          <Plus size={14} />
          Add
        </button>
      </div>

      {/* Progress bar */}
      {subtasks.length > 0 && (
        <div className="h-1.5 w-full rounded-full bg-surface-100">
          <div
            className="h-full rounded-full bg-green-500 transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Subtask list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-4">
          <Loader2 size={16} className="animate-spin text-surface-400" />
        </div>
      ) : (
        <div className="space-y-1">
          {subtasks.map((subtask) => {
            const isDone =
              subtask.status === TaskStatus.DONE ||
              subtask.status === TaskStatus.MERGED;
            return (
              <div
                key={subtask.id}
                className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-surface-50 group"
              >
                <button
                  onClick={() => toggleSubtask(subtask.id, subtask.status)}
                  className="shrink-0 text-surface-400 hover:text-primary-600"
                >
                  {isDone ? (
                    <CheckCircle2 size={16} className="text-green-500" />
                  ) : (
                    <Circle size={16} />
                  )}
                </button>
                <Link
                  to={`/tasks/${subtask.id}`}
                  className={`flex-1 text-sm ${isDone ? "line-through text-surface-400" : "text-surface-700"} hover:text-primary-600`}
                >
                  {subtask.title}
                </Link>
                {subtask.assignee && (
                  <span className="text-xs text-surface-400 truncate max-w-[80px]">
                    {subtask.assignee}
                  </span>
                )}
                <PriorityBadge priority={subtask.priority as Priority} />
              </div>
            );
          })}
        </div>
      )}

      {/* Inline add */}
      {showAdd && (
        <div className="flex items-center gap-2 rounded-lg border border-surface-200 px-2 py-1.5">
          <Circle size={16} className="shrink-0 text-surface-300" />
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleAddSubtask();
              if (e.key === "Escape") {
                setShowAdd(false);
                setNewTitle("");
              }
            }}
            placeholder="Subtask title..."
            className="flex-1 border-none text-sm outline-none placeholder:text-surface-400"
            autoFocus
          />
          <button
            onClick={handleAddSubtask}
            disabled={!newTitle.trim() || createSubtask.isPending}
            className="rounded bg-primary-600 px-2 py-0.5 text-xs text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {createSubtask.isPending ? "..." : "Add"}
          </button>
        </div>
      )}
    </div>
  );
}
