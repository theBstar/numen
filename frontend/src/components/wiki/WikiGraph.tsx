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
  Handle,
  Position,
  type NodeProps,
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
import type { WikiGraphNode, WikiGraphEdge } from "@/types";
import { memo } from "react";

// ── Node colors by type ─────────────────────────────────────────

const NODE_COLORS: Record<string, string> = {
  feature: "#8B5CF6", // purple - primary
  prd: "#3B82F6",     // blue - secondary
  concept: "#F97316", // orange - tertiary
  goal: "#22C55E",    // green
};

const NODE_ICONS: Record<string, string> = {
  feature: "F",
  prd: "P",
  concept: "C",
  goal: "G",
};

function nodeColor(type: string): string {
  return NODE_COLORS[type] ?? "#9CA3AF";
}

// ── Edge colors ─────────────────────────────────────────────────

const EDGE_COLORS: Record<string, string> = {
  references: "#6366F1",
  tagged_to: "#14B8A6",
  implements: "#22C55E",
};

// ── Status border colors ────────────────────────────────────────

const STATUS_BORDER: Record<string, string> = {
  approved: "#16A34A",
  in_progress: "#4F46E5",
  shipped: "#059669",
  draft: "#D1D5DB",
  in_review: "#2563EB",
};

// ── Custom node component ───────────────────────────────────────

interface WikiNodeData {
  wikiNode: WikiGraphNode;
  selected: boolean;
  [key: string]: unknown;
}

const WikiGraphNodeComponent = memo(function WikiGraphNodeInner({
  data,
}: NodeProps<Node<WikiNodeData>>) {
  const { wikiNode, selected } = data;
  const color = nodeColor(wikiNode.type);
  const borderColor = STATUS_BORDER[wikiNode.status] ?? color;
  const size = 36;

  return (
    <>
      <Handle type="target" position={Position.Top} style={{ visibility: "hidden" }} />
      <div
        className="flex items-center justify-center rounded-full border-2 text-white text-xs font-bold cursor-pointer shadow-md transition-all hover:scale-110"
        style={{
          width: size,
          height: size,
          backgroundColor: color,
          borderColor: selected ? "#FFFFFF" : borderColor,
          boxShadow: selected
            ? `0 0 0 3px ${color}, 0 0 12px ${color}80`
            : "0 1px 3px rgba(0,0,0,0.2)",
        }}
        title={`${wikiNode.label} (${wikiNode.type}) - ${wikiNode.status}`}
      >
        {NODE_ICONS[wikiNode.type] ?? "?"}
      </div>
      <div
        className="mt-1 text-center text-[10px] text-surface-600 max-w-[90px] truncate"
        title={wikiNode.label}
      >
        {wikiNode.label}
      </div>
      <Handle type="source" position={Position.Bottom} style={{ visibility: "hidden" }} />
    </>
  );
});

const nodeTypes = { wikiNode: WikiGraphNodeComponent };

// ── Simulation types ────────────────────────────────────────────

interface SimNode extends SimulationNodeDatum {
  id: string;
  wikiNode: WikiGraphNode;
}

// ── Main component ──────────────────────────────────────────────

interface WikiGraphProps {
  graphNodes: WikiGraphNode[];
  graphEdges: WikiGraphEdge[];
  selectedNodeId: string | null;
  onNodeClick: (nodeId: string) => void;
  isLoading: boolean;
}

export function WikiGraph({
  graphNodes,
  graphEdges,
  selectedNodeId,
  onNodeClick,
  isLoading,
}: WikiGraphProps) {
  const simulationRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null);

  const initialNodes = useMemo<Node<WikiNodeData>[]>(
    () =>
      graphNodes.map((gn) => ({
        id: gn.id,
        type: "wikiNode",
        position: { x: Math.random() * 800 - 400, y: Math.random() * 600 - 300 },
        data: {
          wikiNode: gn,
          selected: false,
        },
      })),
    [graphNodes],
  );

  const initialEdges = useMemo<FlowEdge[]>(() => {
    // Deduplicate edges by source+target+type
    const seen = new Set<string>();
    return graphEdges
      .filter((e) => {
        const key = `${e.source}-${e.target}-${e.type}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .map((e, i) => ({
        id: `wiki-edge-${i}`,
        source: e.source,
        target: e.target,
        type: "smoothstep",
        style: {
          stroke: EDGE_COLORS[e.type] ?? "#D1D5DB",
          strokeWidth: 1.5,
          opacity: 0.5,
        },
        label: e.label,
        labelStyle: { fontSize: 9, fill: "#9CA3AF" },
        labelShowBg: false,
      }));
  }, [graphEdges]);

  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState(initialEdges);

  // Sync when data changes
  useEffect(() => {
    setNodes(initialNodes);
  }, [initialNodes, setNodes]);

  useEffect(() => {
    setFlowEdges(initialEdges);
  }, [initialEdges, setFlowEdges]);

  // Force simulation
  useEffect(() => {
    if (graphNodes.length === 0) return;

    simulationRef.current?.stop();

    const nodeIds = new Set(graphNodes.map((n) => n.id));

    const simNodes: SimNode[] = graphNodes.map((gn) => ({
      id: gn.id,
      wikiNode: gn,
      x: Math.random() * 800 - 400,
      y: Math.random() * 600 - 300,
    }));

    const simLinks: SimulationLinkDatum<SimNode>[] = graphEdges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e) => ({ source: e.source, target: e.target }));

    const simulation = forceSimulation<SimNode>(simNodes)
      .force(
        "link",
        forceLink<SimNode, SimulationLinkDatum<SimNode>>(simLinks)
          .id((d) => d.id)
          .distance(140),
      )
      .force("charge", forceManyBody().strength(-350))
      .force("center", forceCenter(0, 0))
      .force("collide", forceCollide().radius(45))
      .alphaDecay(0.02);

    simulationRef.current = simulation;

    simulation.on("tick", () => {
      setNodes((prev) =>
        prev.map((node) => {
          const simNode = simNodes.find((sn) => sn.id === node.id);
          if (simNode && simNode.x != null && simNode.y != null) {
            return { ...node, position: { x: simNode.x, y: simNode.y } };
          }
          return node;
        }),
      );
    });

    const timeout = setTimeout(() => simulation.stop(), 5000);
    return () => {
      clearTimeout(timeout);
      simulation.stop();
    };
  }, [graphNodes, graphEdges, setNodes]);

  // Update selection
  useEffect(() => {
    setNodes((prev) =>
      prev.map((node) => ({
        ...node,
        data: { ...node.data, selected: node.id === selectedNodeId },
      })),
    );
  }, [selectedNodeId, setNodes]);

  const handleNodeClick = useCallback(
    (_: React.MouseEvent, node: Node) => {
      onNodeClick(node.id);
    },
    [onNodeClick],
  );

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-surface-50 text-surface-400">
        <span className="text-sm">Loading graph...</span>
      </div>
    );
  }

  if (graphNodes.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-surface-50 text-surface-400">
        <div className="text-center">
          <p className="text-sm font-medium">No wiki graph data</p>
          <p className="mt-1 text-xs">Create some PRDs and connect them to goals to see the graph.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full w-full">
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
            const data = node.data as WikiNodeData | undefined;
            return data?.wikiNode ? nodeColor(data.wikiNode.type) : "#9CA3AF";
          }}
          position="bottom-left"
          style={{ borderRadius: 8 }}
        />
      </ReactFlow>

      {/* Legend */}
      <div className="absolute right-3 top-3 flex flex-col gap-1 rounded-lg border border-surface-200 bg-white px-3 py-2 shadow-sm">
        <p className="text-[10px] font-semibold uppercase tracking-wider text-surface-400">Legend</p>
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5 text-[10px]">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: color }}
            />
            <span className="capitalize text-surface-600">{type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
