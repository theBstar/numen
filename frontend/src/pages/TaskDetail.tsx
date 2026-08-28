import { useState, useCallback, useMemo } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { ArrowLeft, Trash2, Target, FolderKanban, GitPullRequest, Sparkles, Check, X } from "lucide-react";
import { AiPromptModal } from "@/components/AiPromptModal";
import { StatusTransitionDialog } from "@/components/StatusTransitionDialog";
import { SubtaskList } from "@/components/SubtaskList";
import { TaskActivityPanel } from "@/components/TaskActivityPanel";
import { AttachmentList } from "@/components/AttachmentList";
import { useTask, useMembers, useProjects, useGoals, useLinkSuggestions, useEntities, useEntity } from "@/hooks/queries";
import { useUpdateTask, useCreateEdge, useDeleteEdge, useAcceptSuggestion, useDismissSuggestion } from "@/hooks/mutations";
import { deleteTask, previewPrTransition } from "@/services/api";
import { StatusBadge } from "@/components/StatusBadge";
import { PriorityBadge } from "@/components/PriorityBadge";
import type { Priority } from "@/types";
import { STATUS_OPTIONS, STATUS_TRANSITIONS } from "@/constants/taskStatus";
import {
  InlineEditText,
  InlineEditTextarea,
  InlineEditSelect,
  InlineEditDate,
  InlineEditLabels,
  InlineEditAssignee,
  InlineEditSingleSelect,
  InlineEditMultiSelect,
} from "@/components/InlineEdit";

const sourceConfig: Record<string, { label: string; className: string }> = {
  linear: { label: "Linear", className: "bg-indigo-100 text-indigo-700" },
  github: { label: "GitHub", className: "bg-gray-100 text-gray-700" },
  manual: { label: "Manual", className: "bg-surface-100 text-surface-600" },
};

const priorityOptions = [
  { value: "urgent", label: "Urgent" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  });
}

export function TaskDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { data: task, isLoading, error } = useTask(id!);
  const { data: members } = useMembers();
  const { data: projects } = useProjects();
  const { data: goals } = useGoals();
  const { data: prs } = useEntities({ type: "commit_pr" });
  const { data: entityDetail } = useEntity(id!);
  const updateTaskMutation = useUpdateTask();

  async function save(updates: Record<string, unknown>) {
    await updateTaskMutation.mutateAsync({ id: id!, data: updates });
  }

  async function handleDelete() {
    if (!confirm("Are you sure you want to delete this task?")) return;
    try {
      await deleteTask(id!);
      navigate("/tasks");
    } catch {
      // Error handling
    }
  }

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-4 w-32 animate-pulse rounded bg-surface-200" />
        <div className="h-8 w-64 animate-pulse rounded bg-surface-200" />
        <div className="card animate-pulse h-48" />
      </div>
    );
  }

  if (error || !task) {
    return (
      <div className="flex flex-col items-center py-16 text-center">
        <p className="text-sm font-medium text-surface-600">Task not found</p>
        <Link to="/tasks" className="mt-3 text-sm text-primary-600 hover:underline">Back to Tasks</Link>
      </div>
    );
  }

  const src = sourceConfig[task.source] ?? sourceConfig["manual"]!;

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link to="/tasks" className="inline-flex items-center gap-1.5 text-sm text-surface-500 hover:text-surface-700">
        <ArrowLeft size={16} />
        Back to Tasks
      </Link>

      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <InlineEditSelect
              value={task.status}
              options={[...STATUS_OPTIONS]}
              onSave={(v) => save({ status: v })}
              renderDisplay={(v) => <StatusBadge status={v} />}
            />
            <InlineEditSelect
              value={task.priority}
              options={priorityOptions}
              onSave={(v) => save({ priority: v })}
              renderDisplay={(v) => <PriorityBadge priority={v as Priority} />}
            />
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${src.className}`}>
              {src.label}
            </span>
          </div>
          <InlineEditText
            value={task.title}
            onSave={(v) => save({ title: v })}
            displayClassName="text-2xl font-bold text-surface-900"
            inputClassName="w-full rounded border border-surface-200 px-2 py-1 text-2xl font-bold focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
          />
        </div>
        <button onClick={handleDelete} className="btn-secondary text-red-600 hover:bg-red-50">
          <Trash2 size={14} />
        </button>
      </div>

      {/* Properties */}
      <div className="card">
        <h2 className="text-sm font-semibold text-surface-500 uppercase tracking-wide mb-4">Properties</h2>
        <dl className="grid grid-cols-[140px_1fr] gap-y-3 text-sm">
          <dt className="text-surface-500">Assignee</dt>
          <dd>
            <InlineEditAssignee
              value={task.assignee ?? null}
              members={(members ?? []).map((m) => ({ email: m.email, display_name: m.display_name }))}
              onSave={(v) => save({ assignee_email: v })}
            />
          </dd>

          <dt className="text-surface-500">Due Date</dt>
          <dd>
            <InlineEditDate
              value={task.due_date ?? ""}
              onSave={(v) => save({ due_date: v || null })}
              placeholder="No due date"
            />
          </dd>

          <dt className="text-surface-500">Created</dt>
          <dd className="text-surface-900">{formatDate(task.created_at)}</dd>

          <dt className="text-surface-500">Updated</dt>
          <dd className="text-surface-900">{formatDate(task.updated_at)}</dd>

          <dt className="text-surface-500">Source</dt>
          <dd>
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${src.className}`}>
              {src.label}
            </span>
          </dd>

          <dt className="text-surface-500">Labels</dt>
          <dd>
            <InlineEditLabels
              labels={task.labels}
              onSave={(v) => save({ labels: v })}
            />
          </dd>
        </dl>

        {/* Description */}
        <div className="mt-4 border-t border-surface-100 pt-4">
          <h3 className="text-sm font-medium text-surface-700 mb-2">Description</h3>
          <InlineEditTextarea
            value={task.description ?? ""}
            onSave={(v) => save({ description: v || null })}
            placeholder="Click to add description"
          />
        </div>
      </div>

      {/* Quick Actions */}
      <div className="card">
        <h2 className="text-sm font-semibold text-surface-500 uppercase tracking-wide mb-3">Quick Actions</h2>
        <div className="flex flex-wrap gap-2">
          {(STATUS_TRANSITIONS[task.status] ?? []).map(({ label, next }: { label: string; next: string }) => (
            <button
              key={next}
              onClick={() => save({ status: next })}
              className="btn-secondary text-sm"
            >
              {label}
            </button>
          ))}
          <AiPromptModal taskId={id!} />
        </div>
      </div>

      {/* Linked Entities */}
      <div className="card">
        <h2 className="text-sm font-semibold text-surface-500 uppercase tracking-wide mb-4">Linked Entities</h2>
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-2">
            <FolderKanban size={16} className="text-surface-400" />
            <span className="text-surface-500">Project:</span>
            <InlineEditSingleSelect
              value={task.project_id}
              options={(projects ?? []).map((p) => ({ value: p.id, label: p.name }))}
              onSave={(v) => save({ project_id: v })}
              placeholder="None"
              allowClear
            />
          </div>

          <div className="flex items-start gap-2">
            <Target size={16} className="mt-0.5 text-surface-400" />
            <span className="text-surface-500 mt-0.5">Goals:</span>
            <InlineEditMultiSelect
              values={task.goal_ids}
              options={(goals ?? []).map((g) => ({ value: g.id, label: g.title }))}
              onSave={(v) => save({ goal_ids: v })}
              placeholder="None"
            />
          </div>

          <LinkedPRsSection
            taskId={id!}
            taskStatus={task.status}
            prs={prs ?? null}
            entityDetail={entityDetail ?? null}
            onStatusUpdate={(status: string) => save({ status })}
          />
        </div>
      </div>

      {/* Subtasks */}
      <div className="card">
        <SubtaskList taskId={id!} />
      </div>

      {/* Attachments */}
      <div className="card">
        <AttachmentList taskId={id!} />
      </div>

      {/* Activity / Comments */}
      <div className="card">
        <TaskActivityPanel taskId={id!} />
      </div>
    </div>
  );
}


function LinkedPRsSection({
  taskId,
  taskStatus,
  prs,
  entityDetail,
  onStatusUpdate,
}: {
  taskId: string;
  taskStatus: string;
  prs: import("@/types").Entity[] | null;
  entityDetail: import("@/types").EntityDetailResponse | null;
  onStatusUpdate: (status: string) => void;
}) {
  const { data: suggestions } = useLinkSuggestions("pending");
  const createEdgeMutation = useCreateEdge();
  const deleteEdgeMutation = useDeleteEdge();
  const acceptMutation = useAcceptSuggestion();
  const dismissMutation = useDismissSuggestion();
  const [acting, setActing] = useState<string | null>(null);
  const [pendingTransition, setPendingTransition] = useState<{
    targetStatus: string;
    prName: string;
  } | null>(null);

  // Compute currently linked PR IDs from edges (memoized for stable reference)
  const linkedPrIds = useMemo(
    () =>
      (entityDetail?.edges ?? [])
        .filter((e) => e.type === "ships_to")
        .map((e) => (e.from_entity_id === taskId ? e.to_entity_id : e.from_entity_id)),
    [entityDetail?.edges, taskId],
  );

  // Filter AI suggestions for this task
  const taskSuggestions = (suggestions ?? []).filter(
    (s) => s.target_entity.id === taskId,
  );

  const handlePrChange = useCallback(async (newPrIds: string[]) => {
    const oldSet = new Set(linkedPrIds);
    const newSet = new Set(newPrIds);

    const addedPrIds: string[] = [];

    // Create edges for newly added PRs (skip auto transition for confirmation)
    for (const prId of newPrIds) {
      if (!oldSet.has(prId)) {
        await createEdgeMutation.mutateAsync({
          from_entity_id: prId,
          to_entity_id: taskId,
          type: "ships_to",
          skip_auto_transition: true,
        });
        addedPrIds.push(prId);
      }
    }

    // Delete edges for removed PRs
    for (const prId of linkedPrIds) {
      if (!newSet.has(prId)) {
        await deleteEdgeMutation.mutateAsync({
          from_entity_id: prId,
          to_entity_id: taskId,
          type: "ships_to",
        });
      }
    }

    // Check if any newly linked PR would trigger a status transition
    for (const prId of addedPrIds) {
      try {
        const preview = await previewPrTransition(taskId, prId);
        if (preview?.should_transition) {
          setPendingTransition({
            targetStatus: preview.target_status,
            prName: preview.pr_name,
          });
          break;
        }
      } catch {
        // Preview failed - silently continue, edge is already created
      }
    }
  }, [taskId, linkedPrIds, createEdgeMutation, deleteEdgeMutation]);

  const handleAccept = useCallback(async (suggestionId: string, prEntityId: string) => {
    setActing(suggestionId);
    try {
      await acceptMutation.mutateAsync({ suggestionId, skipAutoTransition: true });

      try {
        const preview = await previewPrTransition(taskId, prEntityId);
        if (preview?.should_transition) {
          setPendingTransition({
            targetStatus: preview.target_status,
            prName: preview.pr_name,
          });
        }
      } catch {
        // Preview failed - silently continue
      }
    } catch {
      // Accept failed
    } finally {
      setActing(null);
    }
  }, [taskId, acceptMutation]);

  const handleDismiss = useCallback(async (id: string) => {
    setActing(id);
    try {
      await dismissMutation.mutateAsync(id);
    } catch (err) {
      console.error("Failed to dismiss suggestion:", err);
    } finally {
      setActing(null);
    }
  }, [dismissMutation]);

  return (
    <>
      <div className="flex items-start gap-2">
        <GitPullRequest size={16} className="mt-0.5 text-surface-400" />
        <span className="text-surface-500 mt-0.5">PRs:</span>
        <InlineEditMultiSelect
          values={linkedPrIds}
          options={(prs ?? []).map((p) => ({ value: p.id, label: p.canonical_name }))}
          onSave={handlePrChange}
          placeholder="None"
        />
      </div>

      {taskSuggestions.length > 0 && (
        <div className="ml-6 mt-1 space-y-1.5">
          <p className="text-xs text-surface-400 flex items-center gap-1">
            <Sparkles size={12} className="text-amber-500" />
            AI suggested
          </p>
          {taskSuggestions.map((s) => {
            const pr = s.source_entity;
            const branch = (pr.properties?.head_branch as string) || "";
            const pct = Math.round(s.confidence * 100);

            return (
              <div
                key={s.id}
                className="flex items-center gap-2 rounded-lg border border-amber-100 bg-amber-50/50 px-2.5 py-2 text-xs"
              >
                <GitPullRequest size={14} className="text-surface-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <Link
                    to={`/entities/${pr.id}`}
                    className="font-medium text-surface-800 hover:text-primary-600 truncate block"
                  >
                    {pr.canonical_name}
                  </Link>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    {branch && (
                      <span className="text-surface-400 font-mono truncate">{branch}</span>
                    )}
                    <span className={`px-1 py-0.5 rounded-full text-[10px] font-medium ${pct >= 80 ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                      {pct}%
                    </span>
                  </div>
                  {s.reasoning && (
                    <p className="text-surface-500 mt-0.5">{s.reasoning}</p>
                  )}
                </div>
                <div className="flex items-center gap-0.5 shrink-0">
                  <button
                    onClick={() => handleAccept(s.id, s.source_entity.id)}
                    disabled={acting === s.id}
                    className="p-1 rounded hover:bg-green-100 text-green-600 disabled:opacity-50"
                    title="Accept link"
                  >
                    <Check size={12} />
                  </button>
                  <button
                    onClick={() => handleDismiss(s.id)}
                    disabled={acting === s.id}
                    className="p-1 rounded hover:bg-red-100 text-red-500 disabled:opacity-50"
                    title="Dismiss"
                  >
                    <X size={12} />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <StatusTransitionDialog
        open={pendingTransition !== null}
        currentStatus={taskStatus}
        targetStatus={pendingTransition?.targetStatus ?? ""}
        prName={pendingTransition?.prName ?? ""}
        onConfirm={() => {
          if (pendingTransition) {
            onStatusUpdate(pendingTransition.targetStatus);
          }
          setPendingTransition(null);
        }}
        onSkip={() => {
          setPendingTransition(null);
        }}
      />
    </>
  );
}
