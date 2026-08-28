import { useState, useMemo, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  DndContext,
  DragOverlay,
  rectIntersection,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragStartEvent,
  type DragEndEvent,
  type DragOverEvent,
  type CollisionDetection,
} from "@dnd-kit/core";
import {
  SortableContext,
  verticalListSortingStrategy,
  useSortable,
} from "@dnd-kit/sortable";
import { useDroppable } from "@dnd-kit/core";
import { CSS } from "@dnd-kit/utilities";
import { Plus } from "lucide-react";
import { PriorityBadge } from "@/components/PriorityBadge";
import { TASK_BOARD_COLUMNS } from "@/constants/taskStatus";
import { cn } from "@/lib/utils";
import type { TaskResponse, Priority, OrgMember } from "@/types";
import { TaskStatus } from "@/types";

const COLUMN_IDS: Set<string> = new Set(TASK_BOARD_COLUMNS.map((c) => c.key));

/**
 * Custom collision detection for Kanban cross-column drops.
 * Prefers card-level hits for accurate insertion positioning,
 * falls back to column-level hits for empty columns or gap areas.
 */
const kanbanCollision: CollisionDetection = (args) => {
  const collisions = rectIntersection(args);
  if (collisions.length === 0) return [];
  const cardHits = collisions.filter((c) => !COLUMN_IDS.has(String(c.id)));
  if (cardHits.length > 0) return cardHits;
  return collisions;
};

interface TaskBoardProps {
  tasks: TaskResponse[];
  onStatusChange: (taskId: string, newStatus: string) => void;
  onQuickCreate?: (title: string, status: string) => void;
  members?: OrgMember[];
  wipLimits?: Record<string, number | null>;
  swimlaneBy?: "none" | "assignee" | "priority";
}

export function TaskBoard({
  tasks,
  onStatusChange,
  onQuickCreate,
  wipLimits = {},
  swimlaneBy = "none",
}: TaskBoardProps) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [overColumnId, setOverColumnId] = useState<string | null>(null);
  const [overIndex, setOverIndex] = useState<number>(0);
  // Refs mirror state to guard against redundant setState calls
  // that cause infinite re-render loops when SortableContext items change
  const overColumnRef = useRef<string | null>(null);
  const overIndexRef = useRef<number>(0);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor),
  );

  const activeTask = useMemo(
    () => tasks.find((t) => t.id === activeId) ?? null,
    [tasks, activeId],
  );

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id));
  }

  function handleDragOver(event: DragOverEvent) {
    const overId = event.over?.id;
    if (!overId) {
      if (overColumnRef.current !== null) {
        overColumnRef.current = null;
        overIndexRef.current = 0;
        setOverColumnId(null);
        setOverIndex(0);
      }
      return;
    }

    const overStr = String(overId);
    let resolvedColumn: string | null;
    let resolvedIndex: number;

    if (COLUMN_IDS.has(overStr)) {
      // Hovering over column background (empty area or gap)
      resolvedColumn = overStr;
      const columnTasks = tasks.filter((t) => t.status === overStr);
      resolvedIndex = columnTasks.length; // append at bottom
    } else {
      // Hovering over a card - find its column and index
      const overTask = tasks.find((t) => t.id === overStr);
      if (!overTask) return;
      resolvedColumn = overTask.status;
      const columnTasks = tasks.filter((t) => t.status === resolvedColumn);
      resolvedIndex = columnTasks.findIndex((t) => t.id === overStr);
      if (resolvedIndex === -1) resolvedIndex = columnTasks.length;
    }

    // Only update state when something actually changed
    if (
      resolvedColumn === overColumnRef.current &&
      resolvedIndex === overIndexRef.current
    ) return;

    overColumnRef.current = resolvedColumn;
    overIndexRef.current = resolvedIndex;
    setOverColumnId(resolvedColumn);
    setOverIndex(resolvedIndex);
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    const targetCol = overColumnRef.current;

    setActiveId(null);
    overColumnRef.current = null;
    overIndexRef.current = 0;
    setOverColumnId(null);
    setOverIndex(0);

    if (!over || !targetCol) return;

    const taskId = String(active.id);
    const draggedTask = tasks.find((t) => t.id === taskId);
    if (!draggedTask || draggedTask.status === targetCol) return;

    onStatusChange(taskId, targetCol);
  }

  function handleDragCancel() {
    setActiveId(null);
    overColumnRef.current = null;
    overIndexRef.current = 0;
    setOverColumnId(null);
    setOverIndex(0);
  }

  // Swimlane logic
  const swimlanes = useMemo(() => {
    if (swimlaneBy === "none") return [{ key: "all", label: "All", tasks }];

    const groups = new Map<string, TaskResponse[]>();

    for (const task of tasks) {
      let key: string;
      if (swimlaneBy === "assignee") {
        key = task.assignee || "Unassigned";
      } else {
        key = task.priority || "medium";
      }
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(task);
    }

    return Array.from(groups.entries()).map(([key, laneTasks]) => ({
      key,
      label: key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, " "),
      tasks: laneTasks,
    }));
  }, [tasks, swimlaneBy]);

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={kanbanCollision}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
      onDragCancel={handleDragCancel}
      autoScroll={{ threshold: { x: 0.15, y: 0.15 }, acceleration: 15 }}
    >
      <div className="space-y-6">
        {swimlanes.map((lane) => (
          <div key={lane.key}>
            {swimlaneBy !== "none" && (
              <div className="mb-3 flex items-center gap-2">
                <h3 className="text-sm font-semibold text-surface-700">{lane.label}</h3>
                <span className="rounded-full bg-surface-100 px-2 py-0.5 text-xs text-surface-500">
                  {lane.tasks.length}
                </span>
              </div>
            )}
            <div className="flex gap-4 overflow-x-auto pb-4">
              {TASK_BOARD_COLUMNS.map((col) => {
                const columnTasks = lane.tasks.filter((t) => t.status === col.key);
                return (
                  <KanbanColumn
                    key={`${lane.key}-${col.key}`}
                    columnKey={col.key}
                    label={col.label}
                    color={col.color}
                    tasks={columnTasks}
                    isOver={overColumnId === col.key}
                    wipLimit={wipLimits[col.key] ?? null}
                    onQuickCreate={onQuickCreate}
                    activeTask={activeTask}
                    overColumnId={overColumnId}
                    overIndex={overIndex}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <DragOverlay dropAnimation={null}>
        {activeTask ? (
          <div className="rotate-1 scale-[1.02] cursor-grabbing">
            <KanbanCardContent task={activeTask} isDragOverlay />
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}

// ── Column ────────────────────────────────────────────────────────────

interface KanbanColumnProps {
  columnKey: string;
  label: string;
  color: string;
  tasks: TaskResponse[];
  isOver: boolean;
  wipLimit: number | null;
  onQuickCreate?: (title: string, status: string) => void;
  activeTask: TaskResponse | null;
  overColumnId: string | null;
  overIndex: number;
}

function KanbanColumn({
  columnKey,
  label,
  color,
  tasks,
  isOver,
  wipLimit,
  onQuickCreate,
  activeTask,
  overColumnId,
  overIndex,
}: KanbanColumnProps) {
  const { setNodeRef } = useDroppable({ id: columnKey });
  const [quickAddTitle, setQuickAddTitle] = useState("");
  const [showQuickAdd, setShowQuickAdd] = useState(false);

  const isOverLimit = wipLimit !== null && tasks.length > wipLimit;
  const isAtLimit = wipLimit !== null && tasks.length === wipLimit;

  // Show a static placeholder when dragging a card from another column
  // into this one. We intentionally do NOT add the active card to
  // SortableContext items - that causes @dnd-kit measureRect loops.
  const isReceiving =
    activeTask &&
    overColumnId === columnKey &&
    activeTask.status !== columnKey;

  function handleQuickAdd() {
    const trimmed = quickAddTitle.trim();
    if (!trimmed || !onQuickCreate) return;
    onQuickCreate(trimmed, columnKey);
    setQuickAddTitle("");
    setShowQuickAdd(false);
  }

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "w-64 shrink-0 rounded-lg transition-all duration-200",
        isOver && "bg-primary-50/50 ring-2 ring-primary-200 ring-inset",
      )}
    >
      {/* Column header */}
      <div className="mb-3 flex items-center gap-2">
        <span className={`h-2 w-2 rounded-full ${color}`} />
        <h3 className="text-sm font-semibold text-surface-700">{label}</h3>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-xs font-medium",
            isOverLimit
              ? "bg-red-100 text-red-700"
              : isAtLimit
                ? "bg-amber-100 text-amber-700"
                : "bg-surface-100 text-surface-500",
          )}
        >
          {tasks.length}
          {wipLimit !== null && `/${wipLimit}`}
        </span>
      </div>

      {/* Cards */}
      <SortableContext
        items={tasks.map((t) => t.id)}
        strategy={verticalListSortingStrategy}
      >
        <div className="space-y-2 min-h-[40px]">
          {tasks.map((task, i) => (
            <div key={task.id}>
              {isReceiving && activeTask && overIndex === i && (
                <div className="mb-2 rounded-lg border-2 border-dashed border-primary-300 bg-primary-50/40 transition-all duration-200">
                  <div className="invisible">
                    <KanbanCardContent task={activeTask} />
                  </div>
                </div>
              )}
              <KanbanCard task={task} />
            </div>
          ))}
          {isReceiving && activeTask && overIndex >= tasks.length && (
            <div className="rounded-lg border-2 border-dashed border-primary-300 bg-primary-50/40 transition-all duration-200">
              <div className="invisible">
                <KanbanCardContent task={activeTask} />
              </div>
            </div>
          )}
          {tasks.length === 0 && !isReceiving && (
            <div className="rounded-lg border border-dashed border-surface-200 p-4 text-center text-xs text-surface-400">
              No tasks
            </div>
          )}
        </div>
      </SortableContext>

      {/* Quick add */}
      {onQuickCreate && (
        <div className="mt-2">
          {showQuickAdd ? (
            <div className="rounded-lg border border-surface-200 bg-white p-2">
              <input
                type="text"
                value={quickAddTitle}
                onChange={(e) => setQuickAddTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleQuickAdd();
                  if (e.key === "Escape") {
                    setShowQuickAdd(false);
                    setQuickAddTitle("");
                  }
                }}
                placeholder="Task title..."
                className="w-full text-sm border-none outline-none placeholder:text-surface-400"
                autoFocus
              />
              <div className="mt-1.5 flex items-center justify-end gap-1.5">
                <button
                  onClick={() => {
                    setShowQuickAdd(false);
                    setQuickAddTitle("");
                  }}
                  className="rounded px-2 py-1 text-xs text-surface-500 hover:bg-surface-100"
                >
                  Cancel
                </button>
                <button
                  onClick={handleQuickAdd}
                  disabled={!quickAddTitle.trim()}
                  className="rounded bg-primary-600 px-2 py-1 text-xs text-white hover:bg-primary-700 disabled:opacity-50"
                >
                  Add
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowQuickAdd(true)}
              className="flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-xs text-surface-400 hover:bg-surface-100 hover:text-surface-600"
            >
              <Plus size={14} />
              Add task
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Sortable Card ─────────────────────────────────────────────────────

function KanbanCard({ task }: { task: TaskResponse }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: task.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  if (isDragging) {
    return (
      <div
        ref={setNodeRef}
        style={style}
        className="rounded-lg border-2 border-dashed border-primary-300 bg-primary-50/40"
      >
        <div className="invisible">
          <KanbanCardContent task={task} />
        </div>
      </div>
    );
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className="cursor-grab active:cursor-grabbing"
    >
      <KanbanCardContent task={task} />
    </div>
  );
}

// ── Card Content (shared between sortable + overlay) ──────────────────

function KanbanCardContent({
  task,
  isDragOverlay = false,
}: {
  task: TaskResponse;
  isDragOverlay?: boolean;
}) {
  const navigate = useNavigate();
  const isOverdue =
    task.due_date &&
    new Date(task.due_date) < new Date() &&
    task.status !== TaskStatus.DONE;

  return (
    <div
      onClick={(e) => {
        if (isDragOverlay) return;
        e.stopPropagation();
        navigate(`/tasks/${task.id}`);
      }}
      className={cn(
        "cursor-pointer rounded-lg border border-surface-200 bg-white p-3 shadow-sm transition-shadow hover:shadow-md",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400 focus-visible:ring-offset-1",
        isDragOverlay && "shadow-xl ring-1 ring-primary-200 border-primary-200",
      )}
      tabIndex={isDragOverlay ? -1 : 0}
      onKeyDown={(e) => {
        if (e.key === "Enter" && !isDragOverlay) {
          navigate(`/tasks/${task.id}`);
        }
      }}
    >
      {/* Title */}
      <p className="text-sm font-medium text-surface-900 line-clamp-2">
        {task.title}
      </p>

      {/* Priority + Story points */}
      <div className="mt-2 flex items-center gap-1.5">
        <PriorityBadge priority={task.priority as Priority} />
        {(task as TaskResponse & { story_points?: number | null }).story_points != null && (
          <span className="rounded bg-surface-100 px-1.5 py-0.5 text-[10px] font-medium text-surface-600">
            {(task as TaskResponse & { story_points?: number }).story_points} SP
          </span>
        )}
      </div>

      {/* Footer: assignee + due date + labels */}
      <div className="mt-2 flex items-center justify-between text-xs text-surface-400">
        <span className="truncate max-w-[100px]">
          {task.assignee || "Unassigned"}
        </span>
        {task.due_date && (
          <span className={cn(isOverdue && "text-red-500 font-medium")}>
            {formatShortDate(task.due_date)}
          </span>
        )}
      </div>

      {/* Labels */}
      {task.labels.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {task.labels.slice(0, 2).map((label) => (
            <span
              key={label}
              className="rounded bg-surface-100 px-1.5 py-0.5 text-[10px] text-surface-500"
            >
              {label}
            </span>
          ))}
          {task.labels.length > 2 && (
            <span className="text-[10px] text-surface-400">
              +{task.labels.length - 2}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function formatShortDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}
