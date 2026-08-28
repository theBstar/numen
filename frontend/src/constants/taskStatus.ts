import { TaskStatus } from "@/types";

/** Ordered pipeline for forward-only task transitions. */
export const TASK_STATUS_PIPELINE = [
  TaskStatus.TODO,
  TaskStatus.IN_PROGRESS,
  TaskStatus.IN_REVIEW,
  TaskStatus.MERGED,
  TaskStatus.DONE,
] as const;

/** Dropdown options for task status selectors. */
export const STATUS_OPTIONS = [
  { value: TaskStatus.TODO, label: "Todo" },
  { value: TaskStatus.IN_PROGRESS, label: "In Progress" },
  { value: TaskStatus.IN_REVIEW, label: "In Review" },
  { value: TaskStatus.MERGED, label: "Merged" },
  { value: TaskStatus.DONE, label: "Done" },
] as const;

/** Quick-action transitions from each status. */
export const STATUS_TRANSITIONS: Record<string, { label: string; next: TaskStatus }[]> = {
  [TaskStatus.TODO]:        [{ label: "Start Working",    next: TaskStatus.IN_PROGRESS }],
  [TaskStatus.IN_PROGRESS]: [{ label: "Move to Review",   next: TaskStatus.IN_REVIEW }],
  [TaskStatus.IN_REVIEW]:   [{ label: "Mark Merged",      next: TaskStatus.MERGED }, { label: "Back to Progress", next: TaskStatus.IN_PROGRESS }],
  [TaskStatus.MERGED]:      [{ label: "Mark Done",        next: TaskStatus.DONE }],
  [TaskStatus.DONE]:        [{ label: "Reopen",           next: TaskStatus.TODO }],
};

/** Badge display config per status. */
export const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  [TaskStatus.BACKLOG]:     { label: "Backlog",     className: "bg-surface-100 text-surface-500" },
  [TaskStatus.TODO]:        { label: "Todo",        className: "bg-gray-100 text-gray-600" },
  [TaskStatus.IN_PROGRESS]: { label: "In Progress", className: "bg-blue-100 text-blue-700" },
  [TaskStatus.IN_REVIEW]:   { label: "In Review",   className: "bg-amber-100 text-amber-700" },
  [TaskStatus.MERGED]:      { label: "Merged",      className: "bg-purple-100 text-purple-700" },
  [TaskStatus.DONE]:        { label: "Done",        className: "bg-green-100 text-green-700" },
};

/** Board column definitions. */
export const TASK_BOARD_COLUMNS = [
  { key: TaskStatus.TODO, label: "To Do", color: "bg-surface-400" },
  { key: TaskStatus.IN_PROGRESS, label: "In Progress", color: "bg-blue-500" },
  { key: TaskStatus.IN_REVIEW, label: "In Review", color: "bg-yellow-500" },
  { key: TaskStatus.MERGED, label: "Merged", color: "bg-purple-500" },
  { key: TaskStatus.DONE, label: "Done", color: "bg-green-500" },
] as const;
