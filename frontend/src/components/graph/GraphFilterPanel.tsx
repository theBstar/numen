import { Search } from "lucide-react";
import { EntityType } from "@/types";
import { nodeColor } from "./ForceGraphNode";

const ENTITY_TYPE_LABELS: Record<string, string> = {
  person: "People",
  task: "Tasks",
  goal: "Goals",
  project: "Projects",
  feature: "Features",
  commit_pr: "PRs",
  incident: "Incidents",
  document: "Documents",
  decision: "Decisions",
  deploy: "Deploys",
  error_event: "Errors",
  metric_snapshot: "Metrics",
};

const EDGE_TYPE_LABELS: Record<string, string> = {
  owns: "Owns",
  blocks: "Blocks",
  depends_on: "Depends on",
  contains: "Contains",
  tagged_to: "Tagged to",
  assigned_to: "Assigned to",
  reports_to: "Reports to",
  authored: "Authored",
  reviews: "Reviews",
  mentioned_in: "Mentioned in",
  ships_to: "Ships to",
  conflicts_with: "Conflicts",
  parent_of: "Parent of",
  measures: "Measures",
  caused_by: "Caused by",
  member_of: "Member of",
  surfaced_to: "Surfaced to",
  acted_on: "Acted on",
  dismissed: "Dismissed",
  approved_by: "Approved by",
  escalated_to: "Escalated to",
  preceded_by: "Preceded by",
  deployed_by: "Deployed by",
};

const EDGE_COLORS: Record<string, string> = {
  blocks: "#EF4444",
  depends_on: "#F97316",
  contains: "#6366F1",
  parent_of: "#8B5CF6",
  tagged_to: "#14B8A6",
  assigned_to: "#3B82F6",
  owns: "#F59E0B",
  reports_to: "#A855F7",
  authored: "#22C55E",
  reviews: "#06B6D4",
  mentioned_in: "#9CA3AF",
  ships_to: "#10B981",
  conflicts_with: "#EF4444",
  measures: "#0EA5E9",
  caused_by: "#DC2626",
  member_of: "#7C3AED",
  surfaced_to: "#2563EB",
  acted_on: "#059669",
  dismissed: "#6B7280",
  approved_by: "#16A34A",
  escalated_to: "#EA580C",
  preceded_by: "#64748B",
  deployed_by: "#0D9488",
};

interface GraphFilterPanelProps {
  entityTypes: string[];
  edgeTypes: string[];
  search: string;
  entityCounts: Record<string, number>;
  onEntityTypesChange: (types: string[]) => void;
  onEdgeTypesChange: (types: string[]) => void;
  onSearchChange: (search: string) => void;
  totalEntities: number;
  totalEdges: number;
}

export function GraphFilterPanel({
  entityTypes,
  edgeTypes,
  search,
  entityCounts,
  onEntityTypesChange,
  onEdgeTypesChange,
  onSearchChange,
  totalEntities,
  totalEdges,
}: GraphFilterPanelProps) {
  const allEntityTypes = Object.values(EntityType);
  const allEdgeTypes = Object.keys(EDGE_TYPE_LABELS);

  const toggleEntityType = (type: string) => {
    if (entityTypes.includes(type)) {
      onEntityTypesChange(entityTypes.filter((t) => t !== type));
    } else {
      onEntityTypesChange([...entityTypes, type]);
    }
  };

  const toggleEdgeType = (type: string) => {
    if (edgeTypes.includes(type)) {
      onEdgeTypesChange(edgeTypes.filter((t) => t !== type));
    } else {
      onEdgeTypesChange([...edgeTypes, type]);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white border-r border-surface-200 w-[240px] shrink-0 overflow-y-auto">
      {/* Header */}
      <div className="p-4 border-b border-surface-200">
        <h2 className="text-sm font-semibold text-surface-900">Context Graph</h2>
        <p className="text-xs text-surface-500 mt-1">
          {totalEntities} entities, {totalEdges} edges
        </p>
      </div>

      {/* Search */}
      <div className="p-3 border-b border-surface-200">
        <div className="relative">
          <Search size={14} className="absolute left-2.5 top-2.5 text-surface-400" />
          <input
            type="text"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search entities..."
            className="w-full pl-8 pr-3 py-2 text-sm border border-surface-200 rounded-lg bg-surface-50 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          />
        </div>
      </div>

      {/* Entity types */}
      <div className="p-3 border-b border-surface-200">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-surface-700 uppercase tracking-wide">Entity Types</span>
          <button
            onClick={() =>
              entityTypes.length === allEntityTypes.length
                ? onEntityTypesChange([])
                : onEntityTypesChange([...allEntityTypes])
            }
            className="text-xs text-primary-600 hover:text-primary-800"
          >
            {entityTypes.length === allEntityTypes.length ? "Clear" : "All"}
          </button>
        </div>
        <div className="space-y-1">
          {allEntityTypes.map((type) => (
            <label key={type} className="flex items-center gap-2 py-1 cursor-pointer group">
              <input
                type="checkbox"
                checked={entityTypes.includes(type)}
                onChange={() => toggleEntityType(type)}
                className="rounded border-surface-300 text-primary-600 focus:ring-primary-500"
              />
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: nodeColor(type) }}
              />
              <span className="text-xs text-surface-700 group-hover:text-surface-900 flex-1">
                {ENTITY_TYPE_LABELS[type] ?? type}
              </span>
              {entityCounts[type] != null && (
                <span className="text-xs text-surface-400">{entityCounts[type]}</span>
              )}
            </label>
          ))}
        </div>
      </div>

      {/* Edge types */}
      <div className="p-3">
        <div className="flex items-center justify-between mb-2">
          <span className="text-xs font-semibold text-surface-700 uppercase tracking-wide">Edge Types</span>
          <button
            onClick={() =>
              edgeTypes.length === allEdgeTypes.length
                ? onEdgeTypesChange([])
                : onEdgeTypesChange([...allEdgeTypes])
            }
            className="text-xs text-primary-600 hover:text-primary-800"
          >
            {edgeTypes.length === allEdgeTypes.length ? "Clear" : "All"}
          </button>
        </div>
        <div className="space-y-1">
          {allEdgeTypes.map((type) => (
            <label key={type} className="flex items-center gap-2 py-1 cursor-pointer group">
              <input
                type="checkbox"
                checked={edgeTypes.includes(type)}
                onChange={() => toggleEdgeType(type)}
                className="rounded border-surface-300 text-primary-600 focus:ring-primary-500"
              />
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: EDGE_COLORS[type] ?? "#9CA3AF" }}
              />
              <span className="text-xs text-surface-700 group-hover:text-surface-900">
                {EDGE_TYPE_LABELS[type] ?? type}
              </span>
            </label>
          ))}
        </div>
      </div>
    </div>
  );
}
