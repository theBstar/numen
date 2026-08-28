import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Pencil, Trash2, Link as LinkIcon } from "lucide-react";
import { useGoal, useEntities } from "@/hooks/queries";
import { useDeleteGoal } from "@/hooks/mutations";
import * as api from "@/services/api";
import { ProgressBar } from "@/components/ProgressBar";
import { GoalForm } from "@/components/GoalForm";
import { EntityLinker } from "@/components/EntityLinker";
import { EntityCard } from "@/components/EntityCard";
import { cn } from "@/lib/utils";
import type { EdgeType } from "@/types";

const levelColors: Record<string, string> = {
  company: "bg-purple-100 text-purple-700",
  team: "bg-blue-100 text-blue-700",
  individual: "bg-emerald-100 text-emerald-700",
};

export function GoalDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: goal, isPending: loading, error, refetch } = useGoal(id!);
  const { data: allEntities } = useEntities();
  const deleteMutation = useDeleteGoal();

  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showEntityLinker, setShowEntityLinker] = useState(false);

  const linkedEntityIds = new Set([
    ...(goal?.linked_project_ids ?? []),
  ]);
  const linkedEntities = (allEntities ?? []).filter((e) => linkedEntityIds.has(e.id));

  const manualProgress =
    goal?.target_value && goal.target_value > 0
      ? Math.round(((goal.current_value ?? 0) / goal.target_value) * 100)
      : 0;

  const overallProgress = goal?.computed_progress ?? manualProgress;

  async function handleDelete() {
    try {
      await deleteMutation.mutateAsync(goal!.id);
      navigate("/goals");
    } catch {
      // Stay on page
    }
  }

  async function handleLinkEntity(entityId: string, edgeType: EdgeType) {
    await api.linkEntityToGoal(goal!.id, entityId, edgeType);
    refetch();
  }

  // Loading state
  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-4 w-32 animate-pulse rounded bg-surface-200" />
        <div className="card animate-pulse space-y-4">
          <div className="h-6 w-48 rounded bg-surface-200" />
          <div className="h-4 w-3/4 rounded bg-surface-200" />
          <div className="h-4 w-1/2 rounded bg-surface-200" />
        </div>
        <div className="card animate-pulse space-y-3">
          <div className="h-4 w-24 rounded bg-surface-200" />
          <div className="h-3 w-full rounded bg-surface-200" />
          <div className="h-3 w-full rounded bg-surface-200" />
        </div>
      </div>
    );
  }

  // Error state
  if (error || !goal) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate("/goals")}
          className="flex items-center gap-1 text-sm text-surface-500 hover:text-surface-700 transition-colors"
        >
          <ArrowLeft size={16} />
          Back to Goals
        </button>
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error ? `Failed to load goal: ${error.message}` : "Goal not found."}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back nav */}
      <button
        onClick={() => navigate("/goals")}
        className="flex items-center gap-1 text-sm text-surface-500 hover:text-surface-700 transition-colors"
      >
        <ArrowLeft size={16} />
        Back to Goals
      </button>

      {/* Header */}
      <div className="card">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <span className={cn("badge", levelColors[goal.level] ?? "bg-surface-100 text-surface-600")}>
                {goal.level}
              </span>
              <span className="badge bg-surface-100 text-surface-600">
                {goal.status}
              </span>
            </div>
            <h1 className="mt-2 text-2xl font-bold text-surface-900">{goal.title}</h1>
            {goal.owner && (
              <p className="mt-1 text-sm text-surface-500">Owner: {goal.owner}</p>
            )}
            {(goal.time_bound_start || goal.time_bound_end) && (
              <p className="mt-1 text-sm text-surface-400">
                {goal.time_bound_start
                  ? new Date(goal.time_bound_start).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                  : "No start date"}
                {" - "}
                {goal.time_bound_end
                  ? new Date(goal.time_bound_end).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
                  : "No end date"}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowEditForm(true)}
              className="btn-secondary"
            >
              <Pencil size={14} className="mr-1.5" />
              Edit
            </button>
            <button
              onClick={() => setShowDeleteConfirm(true)}
              className="flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
            >
              <Trash2 size={14} />
              Delete
            </button>
          </div>
        </div>
      </div>

      {/* Progress */}
      <div className="card space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-surface-400">
          Progress
        </h2>
        <ProgressBar value={overallProgress} label={`${overallProgress}%`} size="md" />
        <div className="flex items-center gap-4 text-xs text-surface-500">
          {goal.target_value != null && (
            <span>Manual: {goal.current_value ?? 0} / {goal.target_value}</span>
          )}
          {goal.computed_progress != null && (
            <span>Computed from tasks: {goal.computed_progress}%</span>
          )}
        </div>
      </div>

      {/* Key Results */}
      <div className="card space-y-4">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-surface-400">
          Key Results
        </h2>
        {goal.key_results.length === 0 ? (
          <p className="text-sm text-surface-400">No key results defined.</p>
        ) : (
          <div className="space-y-3">
            {goal.key_results.map((kr, index) => {
              const krProgress =
                kr.target_value > 0
                  ? Math.round((kr.current_value / kr.target_value) * 100)
                  : 0;

              return (
                <div key={index} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-surface-700">
                      {kr.title}
                    </span>
                    <span className="text-xs text-surface-500">
                      {kr.current_value} / {kr.target_value} {kr.unit}
                    </span>
                  </div>
                  <ProgressBar value={krProgress} />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Linked Items */}
      <div className="card space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-surface-400">
            Linked Items
          </h2>
          <button
            onClick={() => setShowEntityLinker(true)}
            className="btn-secondary text-xs"
          >
            <LinkIcon size={12} className="mr-1" />
            Link Item
          </button>
        </div>

        {linkedEntities.length === 0 ? (
          <p className="text-sm text-surface-400">
            No linked items yet. Link projects and tasks to track progress.
          </p>
        ) : (
          <div className="space-y-2">
            {linkedEntities.map((entity) => (
              <EntityCard key={entity.id} entity={entity} />
            ))}
          </div>
        )}
      </div>

      {/* Delete confirmation */}
      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl">
            <h3 className="text-lg font-semibold text-surface-900">Delete Goal</h3>
            <p className="mt-2 text-sm text-surface-500">
              Are you sure you want to delete &quot;{goal.title}&quot;? This action cannot be undone.
            </p>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setShowDeleteConfirm(false)}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors"
              >
                {deleteMutation.isPending ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit form */}
      {showEditForm && (
        <GoalForm
          goal={goal}
          onClose={() => setShowEditForm(false)}
          onSuccess={() => {
            setShowEditForm(false);
            refetch();
          }}
        />
      )}

      {/* Entity linker */}
      {showEntityLinker && (
        <EntityLinker
          onLink={handleLinkEntity}
          excludeIds={[...linkedEntityIds]}
          onClose={() => setShowEntityLinker(false)}
        />
      )}
    </div>
  );
}
