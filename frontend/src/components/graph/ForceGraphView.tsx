import { useEffect, useMemo, useRef, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge as FlowEdge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import type { Entity, Edge } from "@/types";
import { ForceGraphNode, nodeColor, type ForceNodeData } from "./ForceGraphNode";

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

const nodeTypes = { forceNode: ForceGraphNode };

interface ForceGraphViewProps {
  entities: Entity[];
  edges: Edge[];
  selectedEntityId: string | null;
  onNodeClick: (entityId: string) => void;
}

interface SimNode extends SimulationNodeDatum {
  id: string;
  entity: Entity;
  degree: number;
}

export function ForceGraphView({
  entities,
  edges,
  selectedEntityId,
  onNodeClick,
}: ForceGraphViewProps) {
  const simulationRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null);

  // Compute degree for each entity
  const degreeMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const edge of edges) {
      map.set(edge.from_entity_id, (map.get(edge.from_entity_id) ?? 0) + 1);
      map.set(edge.to_entity_id, (map.get(edge.to_entity_id) ?? 0) + 1);
    }
    return map;
  }, [edges]);

  // Build initial nodes and edges for React Flow
  const initialNodes = useMemo<Node<ForceNodeData>[]>(
    () =>
      entities.map((entity) => ({
        id: entity.id,
        type: "forceNode",
        position: { x: Math.random() * 800 - 400, y: Math.random() * 600 - 300 },
        data: {
          entity,
          degree: degreeMap.get(entity.id) ?? 0,
          selected: false,
        },
      })),
    [entities, degreeMap],
  );

  const initialEdges = useMemo<FlowEdge[]>(
    () =>
      edges.map((edge) => ({
        id: edge.id,
        source: edge.from_entity_id,
        target: edge.to_entity_id,
        type: "smoothstep",
        animated: edge.type === "blocks",
        style: {
          stroke: EDGE_COLORS[edge.type] ?? "#D1D5DB",
          strokeWidth: 1.5,
          opacity: 0.6,
        },
        label: edge.type.replace(/_/g, " "),
        labelStyle: { fontSize: 9, fill: "#9CA3AF" },
        labelShowBg: false,
      })),
    [edges],
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync React Flow state when data changes from API
  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setFlowEdges(initialEdges);
  }, [initialEdges, setFlowEdges]);

  // Run force simulation
  useEffect(() => {
    if (entities.length === 0) return;

    // Stop previous simulation
    simulationRef.current?.stop();

    const entityIds = new Set(entities.map((e) => e.id));

    const simNodes: SimNode[] = entities.map((entity) => ({
      id: entity.id,
      entity,
      degree: degreeMap.get(entity.id) ?? 0,
      x: Math.random() * 800 - 400,
      y: Math.random() * 600 - 300,
    }));

    const simLinks: SimulationLinkDatum<SimNode>[] = edges
      .filter((e) => entityIds.has(e.from_entity_id) && entityIds.has(e.to_entity_id))
      .map((edge) => ({
        source: edge.from_entity_id,
        target: edge.to_entity_id,
      }));

    const simulation = forceSimulation<SimNode>(simNodes)
      .force(
        "link",
        forceLink<SimNode, SimulationLinkDatum<SimNode>>(simLinks)
          .id((d) => d.id)
          .distance(120),
      )
      .force("charge", forceManyBody().strength(-300))
      .force("center", forceCenter(0, 0))
      .force("collide", forceCollide().radius(40))
      .alphaDecay(0.02);

    simulationRef.current = simulation;

    simulation.on("tick", () => {
      setNodes((prev) =>
        prev.map((node) => {
          const simNode = simNodes.find((sn) => sn.id === node.id);
          if (simNode && simNode.x != null && simNode.y != null) {
            return {
              ...node,
              position: { x: simNode.x, y: simNode.y },
            };
          }
          return node;
        }),
      );
    });

    // Stop after stabilization
    const timeout = setTimeout(() => simulation.stop(), 5000);

    return () => {
      clearTimeout(timeout);
      simulation.stop();
    };
  }, [entities, edges, degreeMap, setNodes]);

  // Update selected state when selection changes
  useEffect(() => {
    setNodes((prev) =>
      prev.map((node) => ({
        ...node,
        data: { ...node.data, selected: node.id === selectedEntityId },
      })),
    );
  }, [selectedEntityId, setNodes]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeClick(node.id);
    },
    [onNodeClick],
  );

  if (entities.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-surface-400 bg-surface-50">
        <div className="text-center">
          <p className="text-lg font-medium">No entities found</p>
          <p className="text-sm mt-1">Try adjusting your filters</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 relative">
      <ReactFlow
        nodes={nodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        minZoom={0.1}
        maxZoom={3}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#E5E7EB" gap={20} size={1} />
        <Controls position="bottom-right" />
        <MiniMap
          nodeColor={(node) => {
            const data = node.data as ForceNodeData | undefined;
            return data?.entity ? nodeColor(data.entity.type) : "#9CA3AF";
          }}
          position="bottom-left"
          style={{ borderRadius: 8 }}
        />
      </ReactFlow>
    </div>
  );
}
