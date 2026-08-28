import { useState, useEffect } from "react";
import { useMembers, useGoals } from "@/hooks/queries";
import { SearchableSelect } from "./SearchableSelect";
import { MultiSelectGoals } from "./MultiSelectGoals";
import type { ProjectResponse, ProjectCreateRequest, ProjectUpdateRequest } from "@/types";

interface ProjectFormProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: ProjectCreateRequest | ProjectUpdateRequest) => Promise<void>;
  initialData?: ProjectResponse | null;
  loading?: boolean;
}

export function ProjectForm({ open, onClose, onSubmit, initialData, loading }: ProjectFormProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState("planning");
  const [ownerEmail, setOwnerEmail] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [goalIds, setGoalIds] = useState<string[]>([]);

  const { data: members } = useMembers();
  const { data: goals } = useGoals();

  useEffect(() => {
    if (open) {
      setName(initialData?.name || "");
      setDescription(initialData?.description || "");
      setStatus(initialData?.status || "planning");
      setOwnerEmail(initialData?.owner || "");
      setStartDate(initialData?.start_date?.split("T")[0] || "");
      setEndDate(initialData?.end_date?.split("T")[0] || "");
      setGoalIds(initialData?.goal_ids ?? []);
    }
  }, [open, initialData]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      name: name.trim(),
      description: description.trim() || undefined,
      status,
      owner_email: ownerEmail.trim() || undefined,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
      goal_ids: goalIds.length > 0 ? goalIds : undefined,
    });
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-surface-900">
          {initialData ? "Edit Project" : "Create Project"}
        </h2>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-surface-700">
              Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              maxLength={200}
              className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
              placeholder="e.g., Auth Rewrite"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-surface-700">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
              placeholder="Brief description of the project..."
            />
          </div>

          {/* Status */}
          <div>
            <label className="block text-sm font-medium text-surface-700">Status</label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
            >
              <option value="planning">Planning</option>
              <option value="active">Active</option>
              <option value="paused">Paused</option>
              <option value="completed">Completed</option>
            </select>
          </div>

          {/* Owner */}
          <div>
            <label className="block text-sm font-medium text-surface-700">Owner</label>
            <SearchableSelect
              value={ownerEmail}
              onChange={setOwnerEmail}
              members={(members ?? []).map((m) => ({ email: m.email, display_name: m.display_name }))}
              placeholder="Select owner..."
            />
          </div>

          {/* Goals */}
          <div>
            <label className="block text-sm font-medium text-surface-700">Goals</label>
            <MultiSelectGoals
              value={goalIds}
              onChange={setGoalIds}
              options={(goals ?? []).map((g) => ({ value: g.id, label: g.title }))}
              placeholder="Link to goals..."
            />
          </div>

          {/* Date Range */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-surface-700">Start Date</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-surface-700">End Date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                min={startDate || undefined}
                className="mt-1 w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-surface-200 px-4 py-2 text-sm font-medium text-surface-700 hover:bg-surface-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !name.trim()}
              className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {loading ? "Saving..." : initialData ? "Save Changes" : "Create Project"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
