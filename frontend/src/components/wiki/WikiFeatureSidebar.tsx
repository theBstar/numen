import { useMemo } from "react";
import { Link, useLocation } from "react-router-dom";
import { Layers, Tag } from "lucide-react";
import { WikiSearchBar } from "./WikiSearchBar";
import type { WikiFeatureListItem } from "@/types";

interface WikiFeatureSidebarProps {
  features: WikiFeatureListItem[];
  search: string;
  onSearchChange: (value: string) => void;
}

export function WikiFeatureSidebar({
  features,
  search,
  onSearchChange,
}: WikiFeatureSidebarProps) {
  const location = useLocation();

  const filtered = useMemo(() => {
    if (!search) return features;
    const q = search.toLowerCase();
    return features.filter(
      (f) =>
        f.title.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q) ||
        f.domain_group.toLowerCase().includes(q),
    );
  }, [features, search]);

  // Group by domain_group
  const grouped = useMemo(() => {
    const map = new Map<string, WikiFeatureListItem[]>();
    for (const f of filtered) {
      const group = f.domain_group || "ungrouped";
      const existing = map.get(group) ?? [];
      existing.push(f);
      map.set(group, existing);
    }
    return map;
  }, [filtered]);

  const isActive = (slug: string) =>
    location.pathname === `/wiki/features/${slug}`;

  return (
    <div className="flex h-full flex-col">
      <div className="p-3">
        <WikiSearchBar
          value={search}
          onChange={onSearchChange}
          placeholder="Search features..."
        />
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {filtered.length === 0 ? (
          <p className="px-2 py-4 text-center text-xs text-surface-400">
            {search ? "No features match your search" : "No features generated yet"}
          </p>
        ) : (
          Array.from(grouped.entries()).map(([group, items]) => (
            <div key={group} className="mb-3">
              <div className="flex items-center gap-1.5 px-2 py-1">
                <Layers size={12} className="text-surface-400" />
                <span className="text-[11px] font-medium uppercase tracking-wider text-surface-400">
                  {group === "ungrouped" ? "Other" : group}
                </span>
                <span className="text-[10px] text-surface-300">({items.length})</span>
              </div>
              {items.map((f) => (
                <Link
                  key={f.id}
                  to={`/wiki/features/${f.slug}`}
                  className={`group flex flex-col gap-0.5 rounded-md px-2 py-1.5 text-sm transition-colors ${
                    isActive(f.slug)
                      ? "bg-primary-50 text-primary-700"
                      : "text-surface-700 hover:bg-surface-50"
                  }`}
                >
                  <div className="flex items-center gap-1.5">
                    <span
                      className={`inline-block h-1.5 w-1.5 rounded-full ${
                        f.status === "active"
                          ? "bg-green-400"
                          : f.status === "planned"
                            ? "bg-amber-400"
                            : "bg-surface-300"
                      }`}
                    />
                    <span className="truncate font-medium text-[13px]">{f.title}</span>
                    {f.is_manual && (
                      <Tag size={10} className="shrink-0 text-surface-400" />
                    )}
                  </div>
                  <span className="truncate pl-3 text-xs text-surface-400">
                    {f.description.slice(0, 80)}
                  </span>
                </Link>
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
