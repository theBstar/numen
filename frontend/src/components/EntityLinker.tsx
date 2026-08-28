import { useState, useEffect, useCallback } from "react";
import { Search, X } from "lucide-react";
import { useEntities } from "@/hooks/queries";
import { EntityCard } from "./EntityCard";
import type { EdgeType } from "@/types";

interface EntityLinkerProps {
  onLink: (entityId: string, edgeType: EdgeType) => Promise<void>;
  excludeIds: string[];
  onClose: () => void;
}

const linkableEdgeTypes: { value: EdgeType; label: string }[] = [
  { value: "depends_on", label: "Depends on" },
  { value: "measures", label: "Measures" },
  { value: "tagged_to", label: "Tagged to" },
  { value: "contains", label: "Contains" },
];

export function EntityLinker({ onLink, excludeIds, onClose }: EntityLinkerProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedEdgeType, setSelectedEdgeType] = useState<EdgeType>("depends_on");
  const [linking, setLinking] = useState(false);

  const { data: entities } = useEntities();

  const filteredEntities = (entities ?? []).filter((e) => {
    if (excludeIds.includes(e.id)) return false;
    if (!searchQuery.trim()) return true;
    return e.canonical_name.toLowerCase().includes(searchQuery.toLowerCase());
  });

  const displayedEntities = filteredEntities.slice(0, 20);

  async function handleLink(entityId: string) {
    setLinking(true);
    try {
      await onLink(entityId, selectedEdgeType);
    } finally {
      setLinking(false);
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
        className="w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-surface-900">Link Item</h2>
          <button onClick={onClose} className="text-surface-400 hover:text-surface-600">
            <X size={20} />
          </button>
        </div>

        <div className="mt-4 space-y-3">
          {/* Search */}
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search entities..."
              className={`pl-9 ${inputClass}`}
              autoFocus
            />
          </div>

          {/* Edge type */}
          <select
            value={selectedEdgeType}
            onChange={(e) => setSelectedEdgeType(e.target.value as EdgeType)}
            className={inputClass}
          >
            {linkableEdgeTypes.map((et) => (
              <option key={et.value} value={et.value}>{et.label}</option>
            ))}
          </select>

          {/* Results */}
          {displayedEntities.length === 0 ? (
            <p className="py-8 text-center text-sm text-surface-400">
              {searchQuery ? "No matching entities found." : "Start typing to search for entities."}
            </p>
          ) : (
            <div className="space-y-2">
              {displayedEntities.map((entity) => (
                <div key={entity.id} className="flex items-center gap-2">
                  <div className="flex-1">
                    <EntityCard entity={entity} />
                  </div>
                  <button
                    onClick={() => handleLink(entity.id)}
                    disabled={linking}
                    className="btn-secondary shrink-0 text-xs"
                  >
                    {linking ? "..." : "Link"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
