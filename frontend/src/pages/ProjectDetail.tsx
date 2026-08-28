import { useState, useEffect } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  ArrowLeft,
  Edit2,
  Trash2,
  Plus,
  List,
  LayoutGrid,
  LinkIcon,
} from "lucide-react";
import { useProject, useProjectTasks, useGoals } from "@/hooks/queries";
import {
  useUpdateProject,
  useDeleteProject,
  useCreateTask,
  useUpdateTask,
  useCreateEdge,
} from "@/hooks/mutations";
import { ProjectForm } from "@/components/ProjectForm";
import { TaskBoard } from "@/components/TaskBoard";
import { TaskList } from "@/components/TaskList";
import { TaskStatus } from "@/types";
import type { ProjectUpdateRequest } from "@/types";
import { STATUS_OPTIONS } from "@/constants/taskStatus";
import { cn } from "@/lib/utils";

type ViewMode = "list" | "board";

const statusBadgeColors: Record<string, { bg: string; text: string }> = {
  planning: { bg: "bg-blue-50", text: "text-blue-700" },
  active: { bg: "bg-green-50", text: "text-green-700" },
  paused: { bg: "bg-yellow-50", text: "text-yellow-700" },
  completed: { bg: "bg-surface-100", text: "text-surface-600" },
  archived: { bg: "bg-surface-100", text: "text-surface-400" },
};

export function ProjectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: project, isPending: projectLoading } = useProject(id!);
  const { data: tasks, isPending: tasksLoading } = useProjectTasks(id!);
  const { data: goals } = useGoals();

  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [showGoalLinker, setShowGoalLinker] = useState(false);

  // Task form state
  const [taskTitle, setTaskTitle] = useState("");
  const [taskStatus, setTaskStatus] = useState<string>(TaskStatus.TODO);
  const [taskPriority, setTaskPriority] = useState("medium");
  const [taskAssignee, setTaskAssignee] = useState("");
  const [taskDueDate, setTaskDueDate] = useState("");
  const [taskDescription, setTaskDescription] = useState("");

  // Goal name resolution
  const [goalNames, setGoalNames] = useState<Record<string, string>>({});

  useEffect(() => {
    if (project?.goal_ids && (goals ?? []).length > 0) {
      const names: Record<string, string> = {};
      for (const gid of project.goal_ids) {
        const g = (goals ?? []).find((goal) => goal.id === gid);
        if (g) names[gid] = g.title;
      }
      setGoalNames(names);
    }
  }, [project?.goal_ids, goals]);

  const updateMutation = useUpdateProject();
  const deleteMutation = useDeleteProject();
  const createTaskMutation = useCreateTask();
  const updateTaskMutation = useUpdateTask();
  const linkGoalMutation = useCreateEdge();

  const handleEdit = async (data: ProjectUpdateRequest) => {
    const result = await updateMutation.mutateAsync({
      id: id!,
      data: data as unknown as Record<string, unknown>,
    });
    if (result) {
      setShowEditDialog(false);
    }
  };

  const handleDelete = async () => {
    if (!window.confirm("Archive this project? It will no longer appear in active lists.")) return;
    await deleteMutation.mutateAsync(id!);
    navigate("/projects");
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskTitle.trim()) return;
    const result = await createTaskMutation.mutateAsync({
      title: taskTitle.trim(),
      description: taskDescription.trim() || undefined,
      status: taskStatus,
      priority: taskPriority,
      assignee_email: taskAssignee.trim() || undefined,
      due_date: taskDueDate || undefined,
      project_id: id!,
    });
    if (result) {
      setShowTaskForm(false);
      setTaskTitle("");
      setTaskStatus(TaskStatus.TODO);
      setTaskPriority("medium");
      setTaskAssignee("");
      setTaskDueDate("");
      setTaskDescription("");
    }
  };

  const handleStatusChange = async (taskId: string, newStatus: string) => {
    await updateTaskMutation.mutateAsync({ id: taskId, data: { status: newStatus } });
  };

  const handleLinkGoal = async (goalId: string) => {
    await linkGoalMutation.mutateAsync({
      from_entity_id: id!,
      to_entity_id: goalId,
      type: "tagged_to",
      weight: 1.0,
    });
    setShowGoalLinker(false);
  };

  // Loading state
  if (projectLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 animate-pulse rounded bg-surface-100" />
        <div className="h-4 w-96 animate-pulse rounded bg-surface-100" />
        <div className="h-2 w-full animate-pulse rounded bg-surface-100" />
      </div>
    );
  }

  // Not found
  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <h3 className="text-lg font-semibold text-surface-900">Project not found</h3>
        <p className="mt-1 text-sm text-surface-500">
          This project may have been deleted or you don&apos;t have access.
        </p>
        <Link
          to="/projects"
          className="mt-4 text-sm font-medium text-primary-600 hover:text-primary-700"
        >
          Back to Projects
        </Link>
      </div>
    );
  }

  const percentage = Math.round(
    (project.tasks_done / Math.max(project.task_count, 1)) * 100,
  );
  const badgeColors = (statusBadgeColors[project.status] ?? statusBadgeColors.active)!;

  return (
    <div className="space-y-6">
      {/* Back link */}
      <Link
        to="/projects"
        className="inline-flex items-center gap-1 text-sm text-surface-500 hover:text-surface-700 transition-colors"
      >
        <ArrowLeft size={14} />
        Back to Projects
      </Link>

      {/* Title row */}
      <div className="flex items-start justify-between">
        <h1 className="text-2xl font-bold text-surface-900">{project.name}</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowEditDialog(true)}
            className="flex items-center gap-1.5 rounded-lg border border-surface-200 px-3 py-1.5 text-sm font-medium text-surface-700 hover:bg-surface-50 transition-colors"
          >
            <Edit2 size={14} />
            Edit
          </button>
          <button
            onClick={handleDelete}
            className="flex items-center gap-1.5 rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
          >
            <Trash2 size={14} />
            Delete
          </button>
        </div>
      </div>

      {/* Metadata row */}
      <div className="flex items-center gap-4 text-sm text-surface-500">
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${badgeColors.bg} ${badgeColors.text}`}
        >
          {project.status.charAt(0).toUpperCase() + project.status.slice(1)}
        </span>
        {project.owner && <span>Owner: {project.owner}</span>}
        {(project.start_date || project.end_date) && (
          <span>
            {formatDate(project.start_date)} - {formatDate(project.end_date)}
          </span>
        )}
      </div>

      {/* Goal badges */}
      <div className="flex flex-wrap items-center gap-2">
        {project.goal_ids.map((goalId) => (
          <Link
            key={goalId}
            to={`/entities/${goalId}`}
            className="inline-flex items-center rounded-full bg-primary-50 px-2.5 py-0.5 text-xs font-medium text-primary-700 hover:bg-primary-100 transition-colors"
          >
            {goalNames[goalId] || goalId}
          </Link>
        ))}
        <div className="relative">
          <button
            onClick={() => setShowGoalLinker(!showGoalLinker)}
            className="inline-flex items-center gap-1 rounded-full border border-dashed border-surface-300 px-2.5 py-0.5 text-xs font-medium text-surface-500 hover:border-primary-300 hover:text-primary-600 transition-colors"
          >
            <LinkIcon size={12} />
            Link Goal
          </button>
          {showGoalLinker && (
            <div className="absolute left-0 top-full z-10 mt-1 w-64 rounded-lg border border-surface-200 bg-white p-2 shadow-lg">
              {(goals ?? [])
                .filter((g) => !project.goal_ids.includes(g.id))
                .map((g) => (
                  <button
                    key={g.id}
                    onClick={() => handleLinkGoal(g.id)}
                    className="w-full rounded px-3 py-2 text-left text-sm text-surface-700 hover:bg-surface-100"
                  >
                    {g.title}
                  </button>
                ))}
              {(goals ?? []).filter((g) => !project.goal_ids.includes(g.id)).length === 0 && (
                <p className="px-3 py-2 text-sm text-surface-400">No goals available</p>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-surface-600">Progress</span>
          <span className="font-medium text-surface-900">
            {project.tasks_done}/{project.task_count} tasks ({percentage}%)
          </span>
        </div>
        <div className="mt-1.5 h-2 w-full rounded-full bg-surface-100">
          <div
            className="h-2 rounded-full bg-primary-600 transition-all"
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>

      {/* Description */}
      {project.description && (
        <p className="text-sm text-surface-600">{project.description}</p>
      )}

      {/* View mode toggle + Add Task */}
      <div className="flex items-center justify-between border-b border-surface-200 pb-3">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setViewMode("list")}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
              viewMode === "list"
                ? "bg-primary-50 text-primary-700"
                : "text-surface-500 hover:bg-surface-100",
            )}
          >
            <List size={16} />
            List
          </button>
          <button
            onClick={() => setViewMode("board")}
            className={cn(
              "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
              viewMode === "board"
                ? "bg-primary-50 text-primary-700"
                : "text-surface-500 hover:bg-surface-100",
            )}
          >
            <LayoutGrid size={16} />
            Board
          </button>
        </div>

        <button
          onClick={() => setShowTaskForm(true)}
          className="flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 transition-colors"
        >
          <Plus size={16} />
          Add Task
        </button>
      </div>

      {/* Task views */}
      {tasksLoading ? (
        <div className="space-y-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-12 animate-pulse rounded bg-surface-100" />
          ))}
        </div>
      ) : viewMode === "list" ? (
        <TaskList tasks={tasks ?? []} onStatusChange={handleStatusChange} />
      ) : (
        <TaskBoard tasks={tasks ?? []} onStatusChange={handleStatusChange} />
      )}

      {/* Add task dialog */}
      {showTaskForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
            <h2 className="text-lg font-semibold text-surface-900">Add Task</h2>
            <form onSubmit={handleCreateTask} className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-surface-700">
                  Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  required
                  className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
                  placeholder="Task title"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-surface-700">Status</label>
                  <select
                    value={taskStatus}
                    onChange={(e) => setTaskStatus(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
                  >
                    {STATUS_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-surface-700">Priority</label>
                  <select
                    value={taskPriority}
                    onChange={(e) => setTaskPriority(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
                  >
                    <option value="urgent">Urgent</option>
                    <option value="high">High</option>
                    <option value="medium">Medium</option>
                    <option value="low">Low</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-surface-700">Assignee Email</label>
                <input
                  type="email"
                  value={taskAssignee}
                  onChange={(e) => setTaskAssignee(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
                  placeholder="alice@example.com"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-surface-700">Due Date</label>
                <input
                  type="date"
                  value={taskDueDate}
                  onChange={(e) => setTaskDueDate(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-surface-700">Description</label>
                <textarea
                  value={taskDescription}
                  onChange={(e) => setTaskDescription(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
                  placeholder="Task description..."
                />
              </div>
              <div className="flex justify-end gap-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowTaskForm(false)}
                  className="rounded-lg border border-surface-200 px-4 py-2 text-sm font-medium text-surface-700 hover:bg-surface-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createTaskMutation.isPending || !taskTitle.trim()}
                  className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
                >
                  {createTaskMutation.isPending ? "Creating..." : "Create Task"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit project dialog */}
      <ProjectForm
        open={showEditDialog}
        onClose={() => setShowEditDialog(false)}
        onSubmit={handleEdit}
        initialData={project}
        loading={updateMutation.isPending}
      />
    </div>
  );
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "...";
  return new Date(dateStr).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}
