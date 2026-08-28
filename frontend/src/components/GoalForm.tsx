import { useState, useEffect, useCallback } from "react";
import { X, Plus } from "lucide-react";
import { useGoals, useMembers } from "@/hooks/queries";
import { useCreateGoal, useUpdateGoal } from "@/hooks/mutations";
import { Button } from "@/components/ui/button";
import { SearchableSelect } from "./SearchableSelect";
import type { GoalResponse, GoalLevel } from "@/types";

interface GoalFormProps {
  goal?: GoalResponse;
  onClose: () => void;
  onSuccess: () => void;
}

interface KeyResultInput {
  title: string;
  target_value: number;
  current_value: number;
  unit: string;
}

export function GoalForm({ goal, onClose, onSuccess }: GoalFormProps) {
  const [title, setTitle] = useState(goal?.title ?? "");
  const [level, setLevel] = useState<GoalLevel>(goal?.level ?? "team");
  const [keyResults, setKeyResults] = useState<KeyResultInput[]>(
    goal?.key_results.map(kr => ({ ...kr })) ?? []
  );
  const [targetValue, setTargetValue] = useState(goal?.target_value?.toString() ?? "");
  const [owner, setOwner] = useState(goal?.owner ?? "");
  const [parentGoalId, setParentGoalId] = useState(goal?.parent_goal_id ?? "");
  const [timeBoundStart, setTimeBoundStart] = useState(goal?.time_bound_start?.slice(0, 10) ?? "");
  const [timeBoundEnd, setTimeBoundEnd] = useState(goal?.time_bound_end?.slice(0, 10) ?? "");

  const { data: availableGoals } = useGoals();
  const { data: members } = useMembers();
  const createGoalMutation = useCreateGoal();
  const updateGoalMutation = useUpdateGoal();

  const loading = createGoalMutation.isPending || updateGoalMutation.isPending;

  const parentOptions = (availableGoals ?? []).filter((g) => {
    if (goal && g.id === goal.id) return false;
    if (level === "company") return false;
    if (level === "team") return g.level === "company";
    if (level === "individual") return g.level === "company" || g.level === "team";
    return false;
  });

  function addKR() {
    setKeyResults((prev) => [...prev, { title: "", target_value: 100, current_value: 0, unit: "%" }]);
  }

  function removeKR(index: number) {
    setKeyResults((prev) => prev.filter((_, i) => i !== index));
  }

  function updateKR(index: number, field: keyof KeyResultInput, value: string | number) {
    setKeyResults((prev) =>
      prev.map((kr, i) => (i === index ? { ...kr, [field]: value } : kr))
    );
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;

    const payload = {
      title: title.trim(),
      level,
      key_results: keyResults.filter(kr => kr.title.trim()),
      target_value: targetValue ? Number(targetValue) : undefined,
      owner: owner.trim() || undefined,
      parent_goal_id: parentGoalId || undefined,
      time_bound_start: timeBoundStart || undefined,
      time_bound_end: timeBoundEnd || undefined,
    };

    try {
      if (goal) {
        await updateGoalMutation.mutateAsync({ id: goal.id, data: payload });
      } else {
        await createGoalMutation.mutateAsync(payload);
      }
      onSuccess();
    } catch {
      // Error captured in mutation state
    }
  }

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
  }, [onClose]);

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const inputClass = "w-full rounded-lg border border-surface-200 px-3 py-2 text-sm focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-surface-900">
            {goal ? "Edit Goal" : "Create Goal"}
          </h2>
          <button onClick={onClose} className="text-surface-400 hover:text-surface-600">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-surface-700">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Improve user retention by 15%"
              maxLength={200}
              className={`mt-1 ${inputClass}`}
              required
            />
          </div>

          {/* Level */}
          <div>
            <label className="block text-sm font-medium text-surface-700">Level</label>
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value as GoalLevel)}
              className={`mt-1 ${inputClass}`}
            >
              <option value="company">Company</option>
              <option value="team">Team</option>
              <option value="individual">Individual</option>
            </select>
          </div>

          {/* Parent Goal */}
          {level !== "company" && (
            <div>
              <label className="block text-sm font-medium text-surface-700">Parent Goal</label>
              <select
                value={parentGoalId}
                onChange={(e) => setParentGoalId(e.target.value)}
                className={`mt-1 ${inputClass}`}
              >
                <option value="">No parent</option>
                {parentOptions.map((g) => (
                  <option key={g.id} value={g.id}>{g.title} ({g.level})</option>
                ))}
              </select>
            </div>
          )}

          {/* Key Results */}
          <div>
            <label className="block text-sm font-medium text-surface-700">Key Results</label>
            <div className="mt-2 space-y-2">
              {keyResults.map((kr, index) => (
                <div key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={kr.title}
                    onChange={(e) => updateKR(index, "title", e.target.value)}
                    placeholder="Key result title"
                    className={`flex-1 ${inputClass}`}
                  />
                  <input
                    type="number"
                    value={kr.target_value}
                    onChange={(e) => updateKR(index, "target_value", Number(e.target.value))}
                    placeholder="Target"
                    className={`w-20 ${inputClass}`}
                  />
                  <input
                    type="text"
                    value={kr.unit}
                    onChange={(e) => updateKR(index, "unit", e.target.value)}
                    placeholder="Unit"
                    className={`w-20 ${inputClass}`}
                  />
                  <button type="button" onClick={() => removeKR(index)} className="text-surface-400 hover:text-red-500">
                    <X size={16} />
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={addKR}
                className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700"
              >
                <Plus size={14} />
                Add Key Result
              </button>
            </div>
          </div>

          {/* Target Value */}
          <div>
            <label className="block text-sm font-medium text-surface-700">Target Value</label>
            <input
              type="number"
              value={targetValue}
              onChange={(e) => setTargetValue(e.target.value)}
              placeholder="100"
              className={`mt-1 ${inputClass}`}
            />
          </div>

          {/* Owner */}
          <div>
            <label className="block text-sm font-medium text-surface-700">Owner</label>
            <SearchableSelect
              value={owner}
              onChange={setOwner}
              members={(members ?? []).map((m) => ({ email: m.email, display_name: m.display_name }))}
              placeholder="Select owner..."
            />
          </div>

          {/* Time Bounds */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-surface-700">Start Date</label>
              <input
                type="date"
                value={timeBoundStart}
                onChange={(e) => setTimeBoundStart(e.target.value)}
                className={`mt-1 ${inputClass}`}
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-surface-700">End Date</label>
              <input
                type="date"
                value={timeBoundEnd}
                onChange={(e) => setTimeBoundEnd(e.target.value)}
                className={`mt-1 ${inputClass}`}
              />
            </div>
          </div>

          {/* Actions */}
          <div className="mt-6 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
            <Button type="submit" disabled={loading}>
              {loading ? (goal ? "Saving..." : "Creating...") : (goal ? "Save Changes" : "Create Goal")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
