import { useState } from "react";
import { IterationCcw, ChevronDown } from "lucide-react";
import { useSprints } from "@/hooks/queries";

interface SprintSelectorProps {
  value: string | null;
  onChange: (sprintId: string | null) => void;
}

export function SprintSelector({ value, onChange }: SprintSelectorProps) {
  const { data } = useSprints();
  const [isOpen, setIsOpen] = useState(false);

  const sprints = data?.items ?? [];
  const activeSprint = sprints.find((s) => s.id === value);

  if (sprints.length === 0) return null;

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ${
          value
            ? "border-primary-200 bg-primary-50 text-primary-700"
            : "border-surface-200 bg-white text-surface-600 hover:bg-surface-50"
        }`}
      >
        <IterationCcw size={14} />
        {activeSprint?.name ?? "Sprint"}
        <ChevronDown size={12} />
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute left-0 top-full z-50 mt-1 w-56 rounded-lg border border-surface-200 bg-white p-1 shadow-lg">
            <button
              onClick={() => {
                onChange(null);
                setIsOpen(false);
              }}
              className="flex w-full items-center gap-2 rounded px-3 py-2 text-sm text-surface-600 hover:bg-surface-50"
            >
              All sprints
            </button>
            {sprints.map((sprint) => {
              const progress =
                sprint.story_points_total > 0
                  ? Math.round(
                      (sprint.story_points_done / sprint.story_points_total) * 100,
                    )
                  : 0;
              return (
                <button
                  key={sprint.id}
                  onClick={() => {
                    onChange(sprint.id);
                    setIsOpen(false);
                  }}
                  className={`flex w-full items-center justify-between rounded px-3 py-2 text-sm hover:bg-surface-50 ${
                    sprint.id === value
                      ? "bg-primary-50 text-primary-700 font-medium"
                      : "text-surface-700"
                  }`}
                >
                  <div>
                    <div>{sprint.name}</div>
                    <div className="text-xs text-surface-400">
                      {sprint.task_count} tasks - {progress}%
                    </div>
                  </div>
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                      sprint.status === "active"
                        ? "bg-green-100 text-green-700"
                        : sprint.status === "completed"
                          ? "bg-surface-100 text-surface-500"
                          : "bg-blue-100 text-blue-700"
                    }`}
                  >
                    {sprint.status}
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
