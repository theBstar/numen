import { useMemo, useCallback, type FC } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  type Node,
  type Edge as FlowEdge,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Entity, Edge, EntityType } from "@/types";
import { cn } from "@/lib/utils";
import { GraphLegend } from "./GraphLegend";

// ── Color maps ──

const NODE_COLORS: Record<string, string> = {
  task: "#3B82F6",
  goal: "#8B5CF6",
  project: "#6366F1",
  commit_pr: "#22C55E",
  person: "#F59E0B",
  incident: "#EF4444",
  feature: "#14B8A6",
  document: "#6B7280",
  decision: "#F97316",
  deploy: "#06B6D4",
  error_event: "#EF4444",
  metric_snapshot: "#06B6D4",
};

const EDGE_COLORS: Record<string, string> = {
  blocks: "#EF4444",
  depends_on: "#F97316",
  contains: "#6366F1",
  parent_of: "#8B5CF6",
  tagged_to: "#14B8A6",
  assigned_to: "#3B82F6",
  owns: "#F59E0B",
};

function nodeColor(type: EntityType): string {
  return NODE_COLORS[type] ?? "#9CA3AF";
}

function edgeColor(type: string): string {
  return EDGE_COLORS[type] ?? "#9CA3AF";
}

const TYPE_ICONS: Record<string, string> = {
  task: "T",
  goal: "G",
  project: "P",
  commit_pr: "PR",
  person: "U",
  incident: "!",
  feature: "F",
  document: "D",
  decision: "?",
  deploy: "R",
  error_event: "E",
  metric_snapshot: "M",
};

function formatEdgeLabel(type: string): string {
  return type.replace(/_/g, " ");
}

// ── Custom Node ──

interface EntityNodeData {
  entity: Entity;
  isCenter: boolean;
  [key: string]: unknown;
}

const EntityNode: FC<NodeProps<Node<EntityNodeData>>> = ({ data }) => {
  const { entity, isCenter } = data;
  const color = nodeColor(entity.type);
  const size = isCenter ? 56 : 40;

  return (
    <>
      <Handle type="target" position={Position.Top} style={{ visibility: "hidden" }} />
      <div
        className={cn(
          "flex items-center justify-center rounded-full border-2 text-white text-xs font-bold cursor-pointer shadow-md transition-transform hover:scale-110",
          isCenter && "ring-4 ring-indigo-300",
        )}
        style={{
          width: size,
          height: size,
          backgroundColor: color,
          borderColor: isCenter ? "#4F46E5" : color,
        }}
        title={entity.canonical_name}
      >
        {TYPE_ICONS[entity.type] ?? "?"}
      </div>
      <div
        className="mt-1 text-center text-[10px] text-surface-600 max-w-[80px] truncate"
        title={entity.canonical_name}
      >
        {entity.canonical_name}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ visibility: "hidden" }} />
    </>
  );
};

// ── Layout ──

function layoutNodes(
  nodes: Node<EntityNodeData>[],
  _edges: FlowEdge[],
  centerEntityId: string,
): Node<EntityNodeData>[] {
  const positioned = [...nodes];
  const centerIdx = positioned.findIndex((n) => n.id === centerEntityId);
  const others = positioned.filter((n) => n.id !== centerEntityId);

  if (centerIdx >= 0) {
    positioned[centerIdx] = {
      ...positioned[centerIdx]!,
      position: { x: 0, y: 0 },
    };
  }

  const angleStep = (2 * Math.PI) / Math.max(others.length, 1);
  const radius = 200;

  others.forEach((node, i) => {
    const idx = positioned.findIndex((n) => n.id === node.id);
    if (idx >= 0) {
      positioned[idx] = {
        ...positioned[idx]!,
        position: {
          x: Math.cos(i * angleStep) * radius,
          y: Math.sin(i * angleStep) * radius,
        },
      };
    }
  });

  return positioned;
}

// ── Data transformation ──

function toFlowNodes(entities: Entity[], centerEntityId: string): Node<EntityNodeData>[] {
  return entities.map((entity) => ({
    id: entity.id,
    type: "entityNode",
    position: { x: 0, y: 0 },
    data: {
      entity,
      isCenter: entity.id === centerEntityId,
    },
  }));
}

function toFlowEdges(edges: Edge[]): FlowEdge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.from_entity_id,
    target: edge.to_entity_id,
    type: "smoothstep",
    label: formatEdgeLabel(edge.type),
    animated: false,
    style: { stroke: edgeColor(edge.type) },
    labelStyle: { fontSize: 10, fill: "#6b7280" },
  }));
}

// ── Node types registration ──

const nodeTypes = { entityNode: EntityNode };

// ── Props ──

interface GraphViewProps {
  centerEntityId: string;
  entities: Entity[];
  edges: Edge[];
  onNodeClick?: (entityId: string) => void;
  className?: string;
}

export function GraphView({
  centerEntityId,
  entities,
  edges,
  onNodeClick,
  className,
}: GraphViewProps) {
  const flowEdges = useMemo(() => toFlowEdges(edges), [edges]);

  const flowNodes = useMemo(() => {
    const raw = toFlowNodes(entities, centerEntityId);
    return layoutNodes(raw, flowEdges, centerEntityId);
  }, [entities, edges, centerEntityId, flowEdges]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeClick?.(node.id);
    },
    [onNodeClick],
  );

  if (entities.length === 0) {
    return (
      <div className={cn("flex h-[500px] items-center justify-center text-surface-400 rounded-lg border border-surface-200 bg-white", className)}>
        No graph data available.
      </div>
    );
  }

  return (
    <div>
      <div className={cn("h-[500px] w-full rounded-lg border border-surface-200 bg-white", className)}>
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          onNodeClick={handleNodeClick}
          fitView
          minZoom={0.2}
          maxZoom={2}
        >
          <Background />
          <Controls />
          <MiniMap
            nodeColor={(node) => {
              const data = node.data as EntityNodeData | undefined;
              return data?.entity ? nodeColor(data.entity.type) : "#9CA3AF";
            }}
          />
        </ReactFlow>
      </div>
      <GraphLegend />
    </div>
  );
}
