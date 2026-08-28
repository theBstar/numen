import { X, ExternalLink, ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import type { Entity, Edge } from "@/types";
import { nodeColor } from "./ForceGraphNode";

interface GraphNodeDetailProps {
  entity: Entity;
  edges: Edge[];
  entityMap: Map<string, Entity>;
  onClose: () => void;
}

export function GraphNodeDetail({ entity, edges, entityMap, onClose }: GraphNodeDetailProps) {
  const navigate = useNavigate();
  const color = nodeColor(entity.type);

  const connectedEdges = edges.filter(
    (e) => e.from_entity_id === entity.id || e.to_entity_id === entity.id,
  );

  const props = entity.properties ?? {};
  const displayProps = Object.entries(props).filter(
    ([key]) => !key.startsWith("_") && key !== "embedding",
  );

  return (
    <div className="flex flex-col h-full bg-white border-l border-surface-200 w-[320px] shrink-0 overflow-y-auto">
      {/* Header */}
      <div className="flex items-start justify-between p-4 border-b border-surface-200">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="inline-block px-2 py-0.5 rounded text-xs font-semibold text-white"
              style={{ backgroundColor: color }}
            >
              {entity.type}
            </span>
            <span className="text-xs text-surface-400">{entity.source}</span>
          </div>
          <h3 className="text-sm font-semibold text-surface-900 truncate" title={entity.canonical_name}>
            {entity.canonical_name}
          </h3>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-surface-100 text-surface-400 hover:text-surface-600 shrink-0"
        >
          <X size={16} />
        </button>
      </div>

      {/* Actions */}
      <div className="p-3 border-b border-surface-200">
        <button
          onClick={() => navigate(`/entities/${entity.id}`)}
          className="flex items-center gap-2 w-full px-3 py-2 text-sm text-primary-700 bg-primary-50 rounded-lg hover:bg-primary-100 transition-colors"
        >
          <ExternalLink size={14} />
          View entity detail
        </button>
      </div>

      {/* Properties */}
      {displayProps.length > 0 && (
        <div className="p-3 border-b border-surface-200">
          <h4 className="text-xs font-semibold text-surface-700 uppercase tracking-wide mb-2">Properties</h4>
          <div className="space-y-1.5">
            {displayProps.slice(0, 10).map(([key, value]) => (
              <div key={key} className="flex items-start gap-2">
                <span className="text-xs text-surface-500 shrink-0 w-24 truncate" title={key}>
                  {key}
                </span>
                <span className="text-xs text-surface-800 truncate flex-1" title={String(value)}>
                  {typeof value === "object" ? JSON.stringify(value) : String(value)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Connected edges */}
      <div className="p-3">
        <h4 className="text-xs font-semibold text-surface-700 uppercase tracking-wide mb-2">
          Connections ({connectedEdges.length})
        </h4>
        <div className="space-y-1.5">
          {connectedEdges.slice(0, 20).map((edge) => {
            const isOutgoing = edge.from_entity_id === entity.id;
            const otherId = isOutgoing ? edge.to_entity_id : edge.from_entity_id;
            const other = entityMap.get(otherId);
            const otherName = other?.canonical_name ?? otherId.slice(0, 8);
            const otherColor = other ? nodeColor(other.type) : "#9CA3AF";

            return (
              <div key={edge.id} className="flex items-center gap-1.5 text-xs">
                {isOutgoing ? (
                  <>
                    <span className="text-surface-500 shrink-0">{edge.type.replace(/_/g, " ")}</span>
                    <ArrowRight size={10} className="text-surface-400 shrink-0" />
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: otherColor }}
                    />
                    <span className="text-surface-700 truncate">{otherName}</span>
                  </>
                ) : (
                  <>
                    <span
                      className="w-2 h-2 rounded-full shrink-0"
                      style={{ backgroundColor: otherColor }}
                    />
                    <span className="text-surface-700 truncate">{otherName}</span>
                    <ArrowRight size={10} className="text-surface-400 shrink-0" />
                    <span className="text-surface-500 shrink-0">{edge.type.replace(/_/g, " ")}</span>
                  </>
                )}
              </div>
            );
          })}
          {connectedEdges.length > 20 && (
            <p className="text-xs text-surface-400">+{connectedEdges.length - 20} more</p>
          )}
        </div>
      </div>
    </div>
  );
}
