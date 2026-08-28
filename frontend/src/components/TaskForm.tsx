import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { useMembers, useGoals, useProjects, useTemplates } from "@/hooks/queries";
import { useCreateTask, useUpdateTask } from "@/hooks/mutations";
import { SearchableSelect } from "./SearchableSelect";
import { MultiSelectGoals } from "./MultiSelectGoals";
import { TaskStatus } from "@/types";
import type { TaskResponse, TaskStatus as TaskStatusType, Priority } from "@/types";
import { STATUS_OPTIONS } from "@/constants/taskStatus";

interface TaskFormProps {
  mode: "create" | "edit";
  initialData?: TaskResponse;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
  defaultStatus?: string;
}

const priorityOptions: { value: Priority; label: string }[] = [
  { value: "urgent", label: "Urgent" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

export function TaskForm({ mode, initialData, open, onOpenChange, onSuccess, defaultStatus }: TaskFormProps) {
  const [title, setTitle] = useState(initialData?.title ?? "");
  const [description, setDescription] = useState(initialData?.description ?? "");
  const [status, setStatus] = useState<TaskStatusType>(
    (initialData?.status ?? defaultStatus ?? TaskStatus.TODO) as TaskStatusType,
  );
  const [priority, setPriority] = useState<Priority>(initialData?.priority ?? "medium");
  const [assignee, setAssignee] = useState(initialData?.assignee ?? "");
  const [dueDate, setDueDate] = useState(initialData?.due_date ?? "");
  const [projectId, setProjectId] = useState(initialData?.project_id ?? "");
  const [goalIds, setGoalIds] = useState<string[]>(initialData?.goal_ids ?? []);
  const [labelInput, setLabelInput] = useState("");
  const [labels, setLabels] = useState<string[]>(initialData?.labels ?? []);
  const [storyPoints, setStoryPoints] = useState<string>(
    (initialData as TaskResponse & { story_points?: number | null })?.story_points?.toString() ?? "",
  );
  const [estimatedHours, setEstimatedHours] = useState<string>(
    (initialData as TaskResponse & { estimated_hours?: number | null })?.estimated_hours?.toString() ?? "",
  );
  const [formError, setFormError] = useState<string | null>(null);

  const { data: members } = useMembers();
  const { data: goals } = useGoals();
  const { data: projects } = useProjects();
  const { data: templatesData } = useTemplates();
  const templates = templatesData?.items ?? [];

  const createTask = useCreateTask();
  const updateTask = useUpdateTask();
  const isSubmitting = createTask.isPending || updateTask.isPending;

  function applyTemplate(templateId: string) {
    const template = templates.find((t) => t.id === templateId);
    if (!template) return;
    const props = template.default_properties;
    if (props.status) setStatus(props.status as TaskStatusType);
    if (props.priority) setPriority(props.priority as Priority);
    if (props.labels) setLabels(props.labels as string[]);
    if (props.story_points) setStoryPoints(String(props.story_points));
    if (props.description) setDescription(props.description as string);
  }

  function handleLabelKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      const value = labelInput.trim();
      if (value && !labels.includes(value)) {
        setLabels((prev) => [...prev, value]);
      }
      setLabelInput("");
    }
  }

  function removeLabel(label: string) {
    setLabels((prev) => prev.filter((l) => l !== label));
  }

  async function handleSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    if (!title.trim()) return;
    setFormError(null);

    const payload: Record<string, unknown> = {
      title: title.trim(),
      description: description.trim() || undefined,
      status,
      priority,
      assignee_email: assignee.trim() || undefined,
      due_date: dueDate || undefined,
      project_id: projectId || undefined,
      goal_ids: goalIds.length > 0 ? goalIds : undefined,
      labels,
      story_points: storyPoints ? parseInt(storyPoints, 10) : undefined,
      estimated_hours: estimatedHours ? parseFloat(estimatedHours) : undefined,
    };

    try {
      if (mode === "create") {
        await createTask.mutateAsync(payload as Parameters<typeof createTask.mutateAsync>[0]);
      } else {
        await updateTask.mutateAsync({ id: initialData!.id, data: payload });
      }
      onOpenChange(false);
      onSuccess?.();
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Failed to save task");
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  }

  const inputClass =
    "mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" onKeyDown={handleKeyDown}>
        <DialogHeader>
          <DialogTitle>
            {mode === "create" ? "Create Task" : "Edit Task"}
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-[1fr_280px] gap-6">
          {/* Left column - primary fields */}
          <div className="space-y-4">
            {/* Template selector (create mode only) */}
            {mode === "create" && templates.length > 0 && (
              <div>
                <label className="block text-sm font-medium text-surface-700">
                  Template
                </label>
                <select
                  onChange={(e) => {
                    if (e.target.value) applyTemplate(e.target.value);
                  }}
                  className={inputClass}
                  defaultValue=""
                >
                  <option value="">Start from scratch</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Title */}
            <div>
              <label className="block text-sm font-medium text-surface-700">
                Title *
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Task title"
                className={`${inputClass} text-lg font-medium`}
                maxLength={200}
                required
                autoFocus
              />
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-surface-700">
                Description
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={6}
                placeholder="Add a detailed description..."
                className={inputClass}
              />
            </div>

            {/* Status + Priority */}
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-surface-700">
                  Status *
                </label>
                <select
                  value={status}
                  onChange={(e) =>
                    setStatus(e.target.value as TaskStatusType)
                  }
                  className={inputClass}
                >
                  {STATUS_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-surface-700">
                  Priority *
                </label>
                <select
                  value={priority}
                  onChange={(e) =>
                    setPriority(e.target.value as Priority)
                  }
                  className={inputClass}
                >
                  {priorityOptions.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Right column - metadata sidebar */}
          <div className="space-y-4 md:border-l md:border-surface-100 md:pl-6">
            {/* Assignee */}
            <div>
              <label className="block text-sm font-medium text-surface-700">
                Assignee
              </label>
              <SearchableSelect
                value={assignee}
                onChange={setAssignee}
                members={(members ?? []).map((m: { email: string; display_name: string | null }) => ({
                  email: m.email,
                  display_name: m.display_name,
                }))}
                placeholder="Select assignee..."
              />
            </div>

            {/* Project */}
            <div>
              <label className="block text-sm font-medium text-surface-700">
                Project
              </label>
              <select
                value={projectId}
                onChange={(e) => setProjectId(e.target.value)}
                className={inputClass}
              >
                <option value="">No project</option>
                {(projects ?? []).map(
                  (p: { id: string; name: string }) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ),
                )}
              </select>
            </div>

            {/* Due Date */}
            <div>
              <label className="block text-sm font-medium text-surface-700">
                Due Date
              </label>
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className={inputClass}
              />
            </div>

            {/* Story Points + Estimated Hours */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-sm font-medium text-surface-700">
                  Story Points
                </label>
                <input
                  type="number"
                  min="0"
                  value={storyPoints}
                  onChange={(e) => setStoryPoints(e.target.value)}
                  placeholder="0"
                  className={inputClass}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-surface-700">
                  Est. Hours
                </label>
                <input
                  type="number"
                  min="0"
                  step="0.5"
                  value={estimatedHours}
                  onChange={(e) => setEstimatedHours(e.target.value)}
                  placeholder="0"
                  className={inputClass}
                />
              </div>
            </div>

            {/* Goals */}
            <div>
              <label className="block text-sm font-medium text-surface-700">
                Goals
              </label>
              <MultiSelectGoals
                value={goalIds}
                onChange={setGoalIds}
                options={(goals ?? []).map(
                  (g: { id: string; title: string }) => ({
                    value: g.id,
                    label: g.title,
                  }),
                )}
                placeholder="Link to goals..."
              />
            </div>

            {/* Labels */}
            <div>
              <label className="block text-sm font-medium text-surface-700">
                Labels
              </label>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {labels.map((label) => (
                  <span
                    key={label}
                    className="inline-flex items-center gap-1 rounded-full bg-surface-100 px-2.5 py-0.5 text-xs text-surface-600"
                  >
                    {label}
                    <button
                      type="button"
                      onClick={() => removeLabel(label)}
                      className="text-surface-400 hover:text-surface-600"
                    >
                      &times;
                    </button>
                  </span>
                ))}
              </div>
              <input
                type="text"
                value={labelInput}
                onChange={(e) => setLabelInput(e.target.value)}
                onKeyDown={handleLabelKeyDown}
                placeholder="Type and press Enter to add"
                className={inputClass}
              />
            </div>
          </div>

          {/* Full-width error + actions */}
          <div className="col-span-full">
            {formError && (
              <p className="mb-3 text-sm text-red-600">{formError}</p>
            )}
          </div>
        </form>

        <DialogFooter>
          <div className="flex items-center gap-2">
            <span className="text-xs text-surface-400">
              {navigator.platform.includes("Mac") ? "\u2318" : "Ctrl"}+Enter to submit
            </span>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button
              onClick={() => handleSubmit()}
              disabled={isSubmitting || !title.trim()}
              className="btn-primary disabled:opacity-50"
            >
              {isSubmitting
                ? "Saving..."
                : mode === "create"
                  ? "Create Task"
                  : "Save Changes"}
            </button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
