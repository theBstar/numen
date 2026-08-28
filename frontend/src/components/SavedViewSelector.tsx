import { useState } from "react";
import { Bookmark, Plus, Trash2, Check } from "lucide-react";
import { useSavedViews } from "@/hooks/queries";
import { useCreateSavedView, useDeleteSavedView } from "@/hooks/mutations";
import type { SavedView } from "@/types";

interface SavedViewSelectorProps {
  currentFilters: Record<string, unknown>;
  currentSortConfig: Record<string, unknown>;
  currentViewMode: string;
  currentGroupBy: string | null;
  activeViewId: string | null;
  onApplyView: (view: SavedView) => void;
  onClearView: () => void;
}

export function SavedViewSelector({
  currentFilters,
  currentSortConfig,
  currentViewMode,
  currentGroupBy,
  activeViewId,
  onApplyView,
  onClearView,
}: SavedViewSelectorProps) {
  const { data } = useSavedViews();
  const createView = useCreateSavedView();
  const deleteView = useDeleteSavedView();
  const [isOpen, setIsOpen] = useState(false);
  const [showSaveForm, setShowSaveForm] = useState(false);
  const [newName, setNewName] = useState("");

  const views = data?.items ?? [];

  async function handleSave() {
    const name = newName.trim();
    if (!name) return;
    await createView.mutateAsync({
      name,
      entity_type: "task",
      filters: currentFilters,
      sort_config: currentSortConfig,
      view_mode: currentViewMode,
      group_by: currentGroupBy,
    });
    setNewName("");
    setShowSaveForm(false);
  }

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors ${
          activeViewId
            ? "border-primary-200 bg-primary-50 text-primary-700"
            : "border-surface-200 bg-white text-surface-600 hover:bg-surface-50"
        }`}
      >
        <Bookmark size={14} />
        {activeViewId
          ? views.find((v) => v.id === activeViewId)?.name ?? "Saved View"
          : "Views"}
      </button>

      {isOpen && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setIsOpen(false)}
          />
          <div className="absolute left-0 top-full z-50 mt-1 w-64 rounded-lg border border-surface-200 bg-white p-2 shadow-lg">
            {/* Active view indicator */}
            {activeViewId && (
              <button
                onClick={() => {
                  onClearView();
                  setIsOpen(false);
                }}
                className="mb-1 flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-surface-500 hover:bg-surface-100"
              >
                Clear active view
              </button>
            )}

            {/* View list */}
            {views.length > 0 ? (
              <div className="space-y-0.5">
                {views.map((view) => (
                  <div
                    key={view.id}
                    className="flex items-center justify-between rounded px-2 py-1.5 hover:bg-surface-50 group"
                  >
                    <button
                      onClick={() => {
                        onApplyView(view);
                        setIsOpen(false);
                      }}
                      className="flex flex-1 items-center gap-2 text-sm text-surface-700"
                    >
                      {view.id === activeViewId && (
                        <Check size={14} className="text-primary-600" />
                      )}
                      <span className={view.id === activeViewId ? "font-medium" : ""}>
                        {view.name}
                      </span>
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteView.mutate(view.id);
                      }}
                      className="hidden rounded p-1 text-surface-400 hover:bg-red-50 hover:text-red-500 group-hover:block"
                    >
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            ) : (
              <p className="px-2 py-3 text-center text-xs text-surface-400">
                No saved views
              </p>
            )}

            <div className="mt-1 border-t border-surface-100 pt-1">
              {showSaveForm ? (
                <div className="flex items-center gap-1.5 px-1">
                  <input
                    type="text"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSave();
                      if (e.key === "Escape") setShowSaveForm(false);
                    }}
                    placeholder="View name..."
                    className="flex-1 rounded border border-surface-200 px-2 py-1 text-xs outline-none focus:border-primary-400"
                    autoFocus
                  />
                  <button
                    onClick={handleSave}
                    disabled={!newName.trim()}
                    className="rounded bg-primary-600 px-2 py-1 text-xs text-white hover:bg-primary-700 disabled:opacity-50"
                  >
                    Save
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setShowSaveForm(true)}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm text-surface-600 hover:bg-surface-50"
                >
                  <Plus size={14} />
                  Save current view
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
