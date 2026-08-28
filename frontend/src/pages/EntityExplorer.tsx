import { useState, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { Search } from "lucide-react";
import { EntityType } from "@/types";
import { useEntities } from "@/hooks/queries";
import { EntityCard } from "@/components/EntityCard";
import { cn } from "@/lib/utils";

const filterOptions = [
  { label: "All", value: "" },
  { label: "Tasks", value: EntityType.TASK },
  { label: "PRs", value: EntityType.COMMIT_PR },
  { label: "People", value: EntityType.PERSON },
  { label: "Goals", value: EntityType.GOAL },
  { label: "Projects", value: EntityType.PROJECT },
] as const;

export function EntityExplorer() {
  const [searchParams] = useSearchParams();
  const sourceFilter = searchParams.get("source") ?? "";
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const { data: entities, isPending: loading } = useEntities({
    type: typeFilter || undefined,
    source: sourceFilter || undefined,
    pageSize: 200,
  });

  const filtered = useMemo(() => {
    if (!entities) return [];
    if (!search) return entities;
    const q = search.toLowerCase();
    return entities.filter((e) => e.canonical_name.toLowerCase().includes(q));
  }, [entities, search]);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-surface-900">
        {sourceFilter ? `Entities from ${sourceFilter}` : "Entities"}
      </h1>

      <div className="relative">
        <Search
          size={18}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-surface-400"
        />
        <input
          type="text"
          placeholder="Search entities..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-lg border border-surface-200 bg-white py-2.5 pl-10 pr-4 text-sm placeholder:text-surface-400 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-100"
        />
      </div>

      <div className="flex gap-2 flex-wrap">
        {filterOptions.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setTypeFilter(opt.value)}
            className={cn(
              "rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors",
              typeFilter === opt.value
                ? "bg-primary-600 text-white"
                : "bg-surface-100 text-surface-600 hover:bg-surface-200",
            )}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="card animate-pulse">
              <div className="flex items-center gap-4">
                <div className="h-10 w-10 rounded-lg bg-surface-200" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 w-1/2 rounded bg-surface-200" />
                  <div className="h-3 w-1/4 rounded bg-surface-100" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.length === 0 ? (
            <p className="py-8 text-center text-sm text-surface-400">
              No entities found.
            </p>
          ) : (
            filtered.map((entity) => (
              <EntityCard key={entity.id} entity={entity} />
            ))
          )}
        </div>
      )}
    </div>
  );
}
