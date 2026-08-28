import { useState } from "react";
import { X } from "lucide-react";
import { useUpdateTask } from "@/hooks/mutations";
import { useMembers } from "@/hooks/queries";
import { STATUS_OPTIONS } from "@/constants/taskStatus";

interface BulkActionBarProps {
  selectedIds: string[];
  onClearSelection: () => void;
}

const priorityOptions = [
  { value: "urgent", label: "Urgent" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

export function BulkActionBar({ selectedIds, onClearSelection }: BulkActionBarProps) {
  const updateTask = useUpdateTask();
  const { data: members } = useMembers();
  const [applying, setApplying] = useState(false);

  if (selectedIds.length === 0) return null;

  async function applyBulkUpdate(updates: Record<string, unknown>) {
    setApplying(true);
    try {
      await Promise.all(
        selectedIds.map((id) => updateTask.mutateAsync({ id, data: updates })),
      );
      onClearSelection();
    } finally {
      setApplying(false);
    }
  }

  const memberList = (members ?? []) as { email: string; display_name: string | null }[];

  const selectClass =
    "rounded border border-white/20 bg-white/10 px-2 py-1 text-sm text-white outline-none hover:bg-white/20";

  return (
    <div className="fixed bottom-4 left-1/2 z-50 -translate-x-1/2 animate-in slide-in-from-bottom-4 fade-in">
      <div className="flex items-center gap-3 rounded-xl bg-surface-900 px-4 py-2.5 shadow-2xl">
        <span className="text-sm font-medium text-white">
          {selectedIds.length} selected
        </span>

        <div className="h-4 w-px bg-white/20" />

        {/* Status */}
        <select
          onChange={(e) => {
            if (e.target.value) applyBulkUpdate({ status: e.target.value });
            e.target.value = "";
          }}
          className={selectClass}
          disabled={applying}
          defaultValue=""
        >
          <option value="" disabled>
            Status
          </option>
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        {/* Priority */}
        <select
          onChange={(e) => {
            if (e.target.value) applyBulkUpdate({ priority: e.target.value });
            e.target.value = "";
          }}
          className={selectClass}
          disabled={applying}
          defaultValue=""
        >
          <option value="" disabled>
            Priority
          </option>
          {priorityOptions.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>

        {/* Assignee */}
        <select
          onChange={(e) => {
            if (e.target.value) {
              const email = e.target.value === "__unassign__" ? null : e.target.value;
              applyBulkUpdate({ assignee_email: email });
            }
            e.target.value = "";
          }}
          className={selectClass}
          disabled={applying}
          defaultValue=""
        >
          <option value="" disabled>
            Assignee
          </option>
          <option value="__unassign__">Unassign</option>
          {memberList.map((m) => (
            <option key={m.email} value={m.email}>
              {m.display_name || m.email}
            </option>
          ))}
        </select>

        <div className="h-4 w-px bg-white/20" />

        <button
          onClick={onClearSelection}
          className="flex items-center gap-1 rounded px-2 py-1 text-sm text-white/70 hover:bg-white/10 hover:text-white"
        >
          <X size={14} />
          Deselect
        </button>
      </div>
    </div>
  );
}
