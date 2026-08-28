import { useState } from "react";
import { MessageSquare, Activity, Loader2, Pencil, Trash2 } from "lucide-react";
import { useTaskActivity } from "@/hooks/queries";
import { useAddComment, useEditComment, useDeleteComment } from "@/hooks/mutations";
import { cn } from "@/lib/utils";
import { formatRelativeTime } from "@/lib/utils";

interface TaskActivityPanelProps {
  taskId: string;
}

export function TaskActivityPanel({ taskId }: TaskActivityPanelProps) {
  const { data, isLoading } = useTaskActivity(taskId);
  const addComment = useAddComment();
  const editComment = useEditComment();
  const deleteComment = useDeleteComment();
  const [newComment, setNewComment] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");

  const activities = data?.items ?? [];

  async function handleAddComment() {
    const content = newComment.trim();
    if (!content) return;
    await addComment.mutateAsync({ taskId, content });
    setNewComment("");
  }

  async function handleEditComment(commentId: string) {
    const content = editContent.trim();
    if (!content) return;
    await editComment.mutateAsync({ taskId, commentId, content });
    setEditingId(null);
    setEditContent("");
  }

  function startEditing(activity: { id: string; content: string | null }) {
    setEditingId(activity.id);
    setEditContent(activity.content ?? "");
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-surface-700 flex items-center gap-2">
        <Activity size={16} />
        Activity
      </h3>

      {/* Comment input */}
      <div className="rounded-lg border border-surface-200 p-3">
        <textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment..."
          rows={2}
          className="w-full resize-none border-none text-sm outline-none placeholder:text-surface-400"
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              handleAddComment();
            }
          }}
        />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-xs text-surface-400">
            {navigator.platform.includes("Mac") ? "\u2318" : "Ctrl"}+Enter to submit
          </span>
          <button
            onClick={handleAddComment}
            disabled={!newComment.trim() || addComment.isPending}
            className="rounded bg-primary-600 px-3 py-1 text-xs font-medium text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {addComment.isPending ? "Posting..." : "Comment"}
          </button>
        </div>
      </div>

      {/* Activity list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-6">
          <Loader2 size={20} className="animate-spin text-surface-400" />
        </div>
      ) : activities.length === 0 ? (
        <p className="text-center text-sm text-surface-400 py-4">No activity yet</p>
      ) : (
        <div className="space-y-3">
          {activities.map((activity) => (
            <div
              key={activity.id}
              className={cn(
                "rounded-lg p-3",
                activity.activity_type === "comment"
                  ? "border border-surface-200 bg-white"
                  : "bg-surface-50",
              )}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2 text-xs text-surface-500">
                  {activity.activity_type === "comment" ? (
                    <MessageSquare size={12} />
                  ) : (
                    <Activity size={12} />
                  )}
                  <span className="font-medium text-surface-700">
                    {activity.actor_name || "System"}
                  </span>
                  <span>{formatRelativeTime(activity.created_at)}</span>
                </div>
                {activity.activity_type === "comment" && (
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => startEditing(activity)}
                      className="rounded p-1 text-surface-400 hover:bg-surface-100 hover:text-surface-600"
                    >
                      <Pencil size={12} />
                    </button>
                    <button
                      onClick={() =>
                        deleteComment.mutate({ taskId, commentId: activity.id })
                      }
                      className="rounded p-1 text-surface-400 hover:bg-red-50 hover:text-red-500"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                )}
              </div>

              {editingId === activity.id ? (
                <div className="mt-2">
                  <textarea
                    value={editContent}
                    onChange={(e) => setEditContent(e.target.value)}
                    rows={2}
                    className="w-full rounded border border-surface-200 p-2 text-sm outline-none focus:border-primary-400"
                    autoFocus
                  />
                  <div className="mt-1.5 flex gap-1.5">
                    <button
                      onClick={() => handleEditComment(activity.id)}
                      className="rounded bg-primary-600 px-2 py-1 text-xs text-white hover:bg-primary-700"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="rounded px-2 py-1 text-xs text-surface-500 hover:bg-surface-100"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <p className="mt-1.5 text-sm text-surface-700 whitespace-pre-wrap">
                  {activity.content ||
                    formatActivityDetails(activity.activity_type, activity.details)}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function formatActivityDetails(type: string, details: Record<string, unknown>): string {
  switch (type) {
    case "status_change":
      return `Changed status from ${details.old_value ?? "unknown"} to ${details.new_value ?? "unknown"}`;
    case "assignment_change":
      return `Changed assignee from ${details.old_value ?? "unassigned"} to ${details.new_value ?? "unassigned"}`;
    case "field_change":
      return `Updated ${details.field_name ?? "field"}`;
    default:
      return type.replace(/_/g, " ");
  }
}
