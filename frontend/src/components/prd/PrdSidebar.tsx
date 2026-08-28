import { useState, useCallback, useRef } from "react";
import { Search, X, Filter, FileText, Loader2 } from "lucide-react";
import { usePrdTree } from "@/hooks/prdQueries";
import { PrdTreeNav } from "./PrdTreeNav";
import { cn } from "@/lib/utils";
import { PrdStatus } from "@/types";
import type { PrdStatus as PrdStatusType } from "@/types";

const ALL_STATUSES: { value: PrdStatusType; label: string }[] = [
  { value: PrdStatus.IDEA, label: "Idea" },
  { value: PrdStatus.DRAFT, label: "Draft" },
  { value: PrdStatus.IN_REVIEW, label: "In Review" },
  { value: PrdStatus.APPROVED, label: "Approved" },
  { value: PrdStatus.IN_PROGRESS, label: "In Progress" },
  { value: PrdStatus.SHIPPED, label: "Shipped" },
  { value: PrdStatus.DEPRECATED, label: "Deprecated" },
];

interface PrdSidebarProps {
  selectedId?: string;
  onSelect: (nodeId: string) => void;
}

export function PrdSidebar({ selectedId, onSelect }: PrdSidebarProps) {
  const { data: treeData, isLoading } = usePrdTree();
  const [search, setSearch] = useState("");
  const [localSearch, setLocalSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<PrdStatusType[]>([]);
  const [filterOpen, setFilterOpen] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleSearchChange = useCallback(
    (value: string) => {
      setLocalSearch(value);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setSearch(value), 250);
    },
    [],
  );

  const handleClearSearch = useCallback(() => {
    setLocalSearch("");
    setSearch("");
  }, []);

  const toggleStatus = (status: PrdStatusType) => {
    setStatusFilter((prev) =>
      prev.includes(status)
        ? prev.filter((s) => s !== status)
        : [...prev, status],
    );
  };

  const nodes = treeData?.items ?? [];

  return (
    <>
      {/* Search + Filter */}
      <div className="px-3 py-2 space-y-2">
        <div className="flex items-center gap-1.5">
          <div className="relative flex-1">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-surface-400"
            />
            <input
              type="text"
              value={localSearch}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="Search PRDs..."
              className="w-full rounded-md border border-surface-200 bg-white py-1.5 pl-8 pr-8 text-sm text-surface-800 placeholder:text-surface-400 focus:border-primary-300 focus:outline-none focus:ring-1 focus:ring-primary-300"
            />
            {localSearch && (
              <button
                onClick={handleClearSearch}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-0.5 text-surface-400 hover:text-surface-600"
              >
                <X size={12} />
              </button>
            )}
          </div>

          {/* Filter toggle */}
          <button
            onClick={() => setFilterOpen(!filterOpen)}
            className={cn(
              "flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-md border transition-colors",
              filterOpen || statusFilter.length > 0
                ? "border-primary-300 bg-primary-50 text-primary-600"
                : "border-surface-200 text-surface-400 hover:bg-surface-50 hover:text-surface-600",
            )}
            title="Filter by status"
          >
            <Filter size={14} />
          </button>
        </div>

        {/* Filter dropdown */}
        {filterOpen && (
          <div className="rounded-md border border-surface-200 bg-white p-2 shadow-sm">
            <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-surface-400">
              Status
            </p>
            <div className="flex flex-wrap gap-1">
              {ALL_STATUSES.map((s) => (
                <button
                  key={s.value}
                  onClick={() => toggleStatus(s.value)}
                  className={cn(
                    "rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors",
                    statusFilter.includes(s.value)
                      ? "border-primary-300 bg-primary-50 text-primary-700"
                      : "border-surface-200 text-surface-500 hover:bg-surface-50",
                  )}
                >
                  {s.label}
                </button>
              ))}
            </div>
            {statusFilter.length > 0 && (
              <button
                onClick={() => setStatusFilter([])}
                className="mt-1.5 text-[10px] text-surface-400 hover:text-surface-600"
              >
                Clear filters
              </button>
            )}
          </div>
        )}
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto px-1 py-1">
        {isLoading ? (
          <div className="flex items-center justify-center py-8 text-surface-400">
            <Loader2 size={16} className="animate-spin" />
          </div>
        ) : nodes.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
            <FileText size={20} className="text-surface-300" />
            <p className="text-xs text-surface-400">No PRDs yet</p>
          </div>
        ) : (
          <PrdTreeNav
            nodes={nodes}
            selectedId={selectedId}
            onSelect={onSelect}
            searchFilter={search}
            statusFilter={statusFilter}
          />
        )}
      </div>
    </>
  );
}
