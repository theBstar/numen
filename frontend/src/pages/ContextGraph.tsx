import { useState, useMemo, useCallback } from "react";
import { useFullGraph } from "@/hooks/queries";
import { EntityType, EdgeType } from "@/types";
import { GraphFilterPanel } from "@/components/graph/GraphFilterPanel";
import { ForceGraphView } from "@/components/graph/ForceGraphView";
import { GraphNodeDetail } from "@/components/graph/GraphNodeDetail";
import { Loader2 } from "lucide-react";

const ALL_ENTITY_TYPES = Object.values(EntityType);
const ALL_EDGE_TYPES = Object.values(EdgeType);

export function ContextGraph() {
  const [entityTypes, setEntityTypes] = useState<string[]>([...ALL_ENTITY_TYPES]);
  const [edgeTypes, setEdgeTypes] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);

  // Debounce search
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const searchTimeoutRef = useState<ReturnType<typeof setTimeout> | null>(null);

  const handleSearchChange = useCallback(
    (value: string) => {
      setSearch(value);
      if (searchTimeoutRef[0]) clearTimeout(searchTimeoutRef[0]);
      searchTimeoutRef[0] = setTimeout(() => setDebouncedSearch(value), 300);
    },
    [searchTimeoutRef],
  );

  const { data, isLoading } = useFullGraph({
    entityTypes: entityTypes.length > 0 && entityTypes.length < ALL_ENTITY_TYPES.length ? entityTypes : undefined,
    edgeTypes: edgeTypes.length > 0 && edgeTypes.length < ALL_EDGE_TYPES.length ? edgeTypes : undefined,
    search: debouncedSearch || undefined,
    limit: 500,
  });

  const entities = data?.entities ?? [];
  const edges = data?.edges ?? [];

  // Build entity map for detail panel
  const entityMap = useMemo(() => {
    const map = new Map<string, (typeof entities)[0]>();
    for (const e of entities) map.set(e.id, e);
    return map;
  }, [entities]);

  // Count entities per type
  const entityCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of entities) {
      counts[e.type] = (counts[e.type] ?? 0) + 1;
    }
    return counts;
  }, [entities]);

  const selectedEntity = selectedEntityId ? entityMap.get(selectedEntityId) : null;

  const handleNodeClick = useCallback((entityId: string) => {
    setSelectedEntityId((prev) => (prev === entityId ? null : entityId));
  }, []);

  return (
    <div className="-mx-6 -my-8 flex h-[calc(100vh-0px)]" style={{ marginLeft: "-1.5rem", marginRight: "-1.5rem", marginTop: "-2rem", marginBottom: "-2rem", width: "calc(100% + 3rem)" }}>
      {/* Left: Filter panel */}
      <GraphFilterPanel
        entityTypes={entityTypes}
        edgeTypes={edgeTypes}
        search={search}
        entityCounts={entityCounts}
        onEntityTypesChange={setEntityTypes}
        onEdgeTypesChange={setEdgeTypes}
        onSearchChange={handleSearchChange}
        totalEntities={data?.total_entities ?? 0}
        totalEdges={data?.total_edges ?? 0}
      />

      {/* Center: Graph */}
      {isLoading ? (
        <div className="flex-1 flex items-center justify-center bg-surface-50">
          <div className="flex items-center gap-3 text-surface-500">
            <Loader2 size={20} className="animate-spin" />
            <span className="text-sm">Loading graph...</span>
          </div>
        </div>
      ) : (
        <ForceGraphView
          entities={entities}
          edges={edges}
          selectedEntityId={selectedEntityId}
          onNodeClick={handleNodeClick}
        />
      )}

      {/* Right: Detail panel */}
      {selectedEntity && (
        <GraphNodeDetail
          entity={selectedEntity}
          edges={edges}
          entityMap={entityMap}
          onClose={() => setSelectedEntityId(null)}
        />
      )}
    </div>
  );
}
