import { useState, useMemo, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Plus,
  ListFilter,
  CheckSquare,
  List,
  Columns3,
  Search,
  X,
} from "lucide-react";
import { useTasks, useMembers, useKanbanSettings } from "@/hooks/queries";
import { useUpdateTask, useCreateTask } from "@/hooks/mutations";
import { TaskCard } from "@/components/TaskCard";
import { TaskBoard } from "@/components/TaskBoard";
import { TaskForm } from "@/components/TaskForm";
import { BulkActionBar } from "@/components/BulkActionBar";
import { TaskGroupHeader } from "@/components/TaskGroupHeader";
import { SavedViewSelector } from "@/components/SavedViewSelector";
import { SprintSelector } from "@/components/SprintSelector";
import { EmptyState } from "@/components/EmptyState";
import { cn } from "@/lib/utils";
import type { TaskStatus, Priority, TaskResponse, SavedView } from "@/types";
import { STATUS_OPTIONS } from "@/constants/taskStatus";

const priorityOptions: { value: Priority; label: string }[] = [
  { value: "urgent", label: "Urgent" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

type SortBy = "due_date" | "priority" | "created_at";
type GroupBy = "none" | "status" | "priority" | "assignee" | "project";
type ViewMode = "list" | "board";

function getStoredView(): ViewMode {
  return (localStorage.getItem("numen_tasks_view_mode") as ViewMode) || "list";
}

export function Tasks() {
  const navigate = useNavigate();
  const searchInputRef = useRef<HTMLInputElement>(null);

  // View state
  const [viewMode, setViewMode] = useState<ViewMode>(getStoredView);
  const [showCreateForm, setShowCreateForm] = useState(false);

  // Filter state
  const [statusFilter, setStatusFilter] = useState<TaskStatus[]>([]);
  const [priorityFilter, setPriorityFilter] = useState<Priority | "all">("all");
  const [assigneeFilter, setAssigneeFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [sprintFilter, setSprintFilter] = useState<string | null>(null);

  // List view state
  const [sortBy, setSortBy] = useState<SortBy>("due_date");
  const [groupBy, setGroupBy] = useState<GroupBy>("none");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());

  // Bulk selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Saved views
  const [activeViewId, setActiveViewId] = useState<string | null>(null);

  // Board swimlanes
  const [swimlaneBy, setSwimlaneBy] = useState<"none" | "assignee" | "priority">("none");

  // Data
  const { data: tasksData, isLoading } = useTasks();
  const { data: membersData } = useMembers();
  const { data: kanbanData } = useKanbanSettings();
  const updateTask = useUpdateTask();
  const createTask = useCreateTask();

  const tasks = (tasksData ?? []) as TaskResponse[];
  const members = (membersData ?? []) as { email: string; display_name: string | null }[];

  // WIP limits map
  const wipLimits = useMemo(() => {
    const limits: Record<string, number | null> = {};
    for (const item of kanbanData?.items ?? []) {
      limits[item.column_status] = item.wip_limit;
    }
    return limits;
  }, [kanbanData]);

  // Persist view mode
  useEffect(() => {
    localStorage.setItem("numen_tasks_view_mode", viewMode);
  }, [viewMode]);

  // Unique assignees
  const assignees = useMemo(() => {
    const set = new Set<string>();
    for (const t of tasks) {
      if (t.assignee) set.add(t.assignee);
    }
    return Array.from(set).sort();
  }, [tasks]);

  // Status counts for filter pills
  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of tasks) {
      counts[t.status] = (counts[t.status] ?? 0) + 1;
    }
    return counts;
  }, [tasks]);

  // Filtered tasks
  const filtered = useMemo(() => {
    let result = tasks;

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      result = result.filter((t) => t.title.toLowerCase().includes(q));
    }
    if (statusFilter.length > 0) {
      result = result.filter((t) => statusFilter.includes(t.status));
    }
    if (priorityFilter !== "all") {
      result = result.filter((t) => t.priority === priorityFilter);
    }
    if (assigneeFilter !== "all") {
      result = result.filter((t) =>
        assigneeFilter === "unassigned" ? !t.assignee : t.assignee === assigneeFilter,
      );
    }
    return result;
  }, [tasks, searchQuery, statusFilter, priorityFilter, assigneeFilter]);

  // Sorted (list view only)
  const sorted = useMemo(() => {
    if (viewMode === "board") {
      return [...filtered].sort(
        (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      );
    }

    const priorityOrder: Record<string, number> = {
      urgent: 0,
      high: 1,
      medium: 2,
      low: 3,
    };

    return [...filtered].sort((a, b) => {
      switch (sortBy) {
        case "due_date":
          if (!a.due_date && !b.due_date) return 0;
          if (!a.due_date) return 1;
          if (!b.due_date) return -1;
          return new Date(a.due_date).getTime() - new Date(b.due_date).getTime();
        case "priority":
          return (priorityOrder[a.priority] ?? 2) - (priorityOrder[b.priority] ?? 2);
        case "created_at":
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        default:
          return 0;
      }
    });
  }, [filtered, sortBy, viewMode]);

  // Grouped (list view only)
  const groups = useMemo(() => {
    if (groupBy === "none" || viewMode === "board") {
      return [{ key: "all", label: "All", tasks: sorted }];
    }

    const map = new Map<string, TaskResponse[]>();
    for (const task of sorted) {
      let key: string;
      switch (groupBy) {
        case "status":
          key = task.status;
          break;
        case "priority":
          key = task.priority;
          break;
        case "assignee":
          key = task.assignee || "Unassigned";
          break;
        case "project":
          key = task.project_id || "No Project";
          break;
        default:
          key = "all";
      }
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(task);
    }

    return Array.from(map.entries()).map(([key, groupTasks]) => ({
      key,
      label: key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, " "),
      tasks: groupTasks,
    }));
  }, [sorted, groupBy, viewMode]);

  function toggleStatus(s: TaskStatus) {
    setStatusFilter((prev) =>
      prev.includes(s) ? prev.filter((v) => v !== s) : [...prev, s],
    );
  }

  function toggleGroupCollapsed(key: string) {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleSelected(taskId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(taskId)) next.delete(taskId);
      else next.add(taskId);
      return next;
    });
  }

  function selectAll() {
    setSelectedIds(new Set(sorted.map((t) => t.id)));
  }

  function handleStatusChange(taskId: string, newStatus: string) {
    updateTask.mutate({ id: taskId, data: { status: newStatus } });
  }

  function handleQuickCreate(title: string, status: string) {
    createTask.mutate({ title, status, priority: "medium" });
  }

  function applyView(view: SavedView) {
    setActiveViewId(view.id);
    const f = view.filters as Record<string, unknown>;
    if (f.statusFilter) setStatusFilter(f.statusFilter as TaskStatus[]);
    if (f.priorityFilter) setPriorityFilter(f.priorityFilter as Priority | "all");
    if (f.assigneeFilter) setAssigneeFilter(f.assigneeFilter as string);
    if (view.view_mode) setViewMode(view.view_mode as ViewMode);
    if (view.group_by) setGroupBy(view.group_by as GroupBy);
  }

  function clearView() {
    setActiveViewId(null);
    setStatusFilter([]);
    setPriorityFilter("all");
    setAssigneeFilter("all");
    setSearchQuery("");
    setGroupBy("none");
  }

  const hasActiveFilters =
    statusFilter.length > 0 ||
    priorityFilter !== "all" ||
    assigneeFilter !== "all" ||
    searchQuery !== "";

  const selectClass = "rounded-lg border border-surface-200 px-3 py-2 text-sm bg-white";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-surface-900">Tasks</h1>
          <p className="mt-1 text-surface-500">
            View and manage tasks across all projects.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="flex items-center gap-1 rounded-lg bg-surface-100 p-1">
            <button
              onClick={() => setViewMode("list")}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-all",
                viewMode === "list"
                  ? "bg-white text-surface-900 shadow-sm"
                  : "text-surface-500 hover:text-surface-700",
              )}
            >
              <List size={14} />
              List
            </button>
            <button
              onClick={() => setViewMode("board")}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-all",
                viewMode === "board"
                  ? "bg-white text-surface-900 shadow-sm"
                  : "text-surface-500 hover:text-surface-700",
              )}
            >
              <Columns3 size={14} />
              Board
            </button>
          </div>

          <button
            onClick={() => setShowCreateForm(true)}
            className="btn-primary"
          >
            <Plus size={16} className="mr-1.5" />
            Create Task
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Search */}
        <div className="relative">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"
          />
          <input
            ref={searchInputRef}
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search tasks..."
            className="rounded-lg border border-surface-200 bg-white pl-9 pr-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100 w-52"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-surface-400 hover:text-surface-600"
            >
              <X size={14} />
            </button>
          )}
        </div>

        {/* Status pills */}
        <div className="flex items-center gap-1.5">
          {STATUS_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => toggleStatus(o.value)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                statusFilter.includes(o.value)
                  ? "bg-primary-100 text-primary-700"
                  : "bg-surface-100 text-surface-500 hover:bg-surface-200",
              )}
            >
              {o.label}
              <span className="ml-1 text-[10px] opacity-60">
                {statusCounts[o.value] ?? 0}
              </span>
            </button>
          ))}
        </div>

        {/* Priority filter */}
        <select
          value={priorityFilter}
          onChange={(e) =>
            setPriorityFilter(e.target.value as Priority | "all")
          }
          className={selectClass}
          aria-label="Filter by priority"
        >
          <option value="all">All Priorities</option>
          {priorityOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        {/* Assignee filter */}
        <select
          value={assigneeFilter}
          onChange={(e) => setAssigneeFilter(e.target.value)}
          className={selectClass}
          aria-label="Filter by assignee"
        >
          <option value="all">All Assignees</option>
          <option value="unassigned">Unassigned</option>
          {assignees.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>

        {/* Sprint filter */}
        <SprintSelector value={sprintFilter} onChange={setSprintFilter} />

        {/* Saved views */}
        <SavedViewSelector
          currentFilters={{
            statusFilter,
            priorityFilter,
            assigneeFilter,
          }}
          currentSortConfig={{ sortBy }}
          currentViewMode={viewMode}
          currentGroupBy={groupBy}
          activeViewId={activeViewId}
          onApplyView={applyView}
          onClearView={clearView}
        />

        {/* Clear filters */}
        {hasActiveFilters && (
          <button
            onClick={clearView}
            className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-surface-500 hover:bg-surface-100 hover:text-surface-700"
          >
            <X size={12} />
            Clear filters
          </button>
        )}

        {/* Right-aligned controls */}
        <div className="ml-auto flex items-center gap-2">
          {/* Sort (list view only) */}
          {viewMode === "list" && (
            <>
              <select
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value as GroupBy)}
                className={selectClass}
                aria-label="Group by"
              >
                <option value="none">No Grouping</option>
                <option value="status">Group: Status</option>
                <option value="priority">Group: Priority</option>
                <option value="assignee">Group: Assignee</option>
                <option value="project">Group: Project</option>
              </select>

              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortBy)}
                className={selectClass}
                aria-label="Sort tasks"
              >
                <option value="due_date">Sort: Due Date</option>
                <option value="priority">Sort: Priority</option>
                <option value="created_at">Sort: Created</option>
              </select>
            </>
          )}

          {/* Swimlane (board view only) */}
          {viewMode === "board" && (
            <select
              value={swimlaneBy}
              onChange={(e) =>
                setSwimlaneBy(e.target.value as "none" | "assignee" | "priority")
              }
              className={selectClass}
              aria-label="Swimlanes"
            >
              <option value="none">No Swimlanes</option>
              <option value="assignee">Swimlane: Assignee</option>
              <option value="priority">Swimlane: Priority</option>
            </select>
          )}
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-3" aria-busy="true">
          {[1, 2, 3].map((i) => (
            <div key={i} className="card animate-pulse h-20" />
          ))}
        </div>
      ) : tasks.length === 0 ? (
        <EmptyState
          icon={CheckSquare}
          title="No tasks yet"
          description="Tasks will appear when you connect integrations like Linear or create them manually."
          action={{
            label: "Create Task",
            onClick: () => setShowCreateForm(true),
          }}
          secondaryAction={{
            label: "Connect your tools first",
            onClick: () => navigate("/connections"),
          }}
        />
      ) : viewMode === "board" ? (
        /* Board view */
        <TaskBoard
          tasks={sorted}
          onStatusChange={handleStatusChange}
          onQuickCreate={handleQuickCreate}
          wipLimits={wipLimits}
          swimlaneBy={swimlaneBy}
        />
      ) : filtered.length === 0 ? (
        <div className="card flex flex-col items-center py-12 text-center">
          <ListFilter size={40} className="text-surface-300" />
          <p className="mt-3 text-sm font-medium text-surface-600">
            No tasks found
          </p>
          <p className="mt-1 text-sm text-surface-400">
            Try adjusting your filters or create a new task.
          </p>
        </div>
      ) : (
        /* List view */
        <div className="space-y-2">
          {/* Select all */}
          {sorted.length > 0 && selectedIds.size > 0 && (
            <div className="flex items-center gap-2 px-1">
              <button
                onClick={selectAll}
                className="text-xs text-primary-600 hover:underline"
              >
                Select all ({sorted.length})
              </button>
            </div>
          )}

          {groups.map((group) => (
            <div key={group.key}>
              {groupBy !== "none" && (
                <TaskGroupHeader
                  label={group.label}
                  count={group.tasks.length}
                  isExpanded={!collapsedGroups.has(group.key)}
                  onToggle={() => toggleGroupCollapsed(group.key)}
                />
              )}
              {(groupBy === "none" || !collapsedGroups.has(group.key)) && (
                <div className="space-y-2">
                  {group.tasks.map((task) => (
                    <div key={task.id} className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={selectedIds.has(task.id)}
                        onChange={() => toggleSelected(task.id)}
                        className="h-4 w-4 rounded border-surface-300 text-primary-600 focus:ring-primary-500 shrink-0"
                        onClick={(e) => e.stopPropagation()}
                      />
                      <div className="flex-1">
                        <TaskCard
                          task={task}
                          onUpdate={async (taskId, updates) => {
                            await updateTask.mutateAsync({ id: taskId, data: updates });
                          }}
                          members={members as unknown as import("@/types").OrgMember[]}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Bulk action bar */}
      <BulkActionBar
        selectedIds={Array.from(selectedIds)}
        onClearSelection={() => setSelectedIds(new Set())}
      />

      {/* Create form dialog */}
      <TaskForm
        mode="create"
        open={showCreateForm}
        onOpenChange={setShowCreateForm}
        onSuccess={() => setShowCreateForm(false)}
      />
    </div>
  );
}
