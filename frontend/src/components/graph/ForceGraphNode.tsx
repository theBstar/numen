import { memo, type FC } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import type { Entity, EntityType } from "@/types";

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

export function nodeColor(type: EntityType): string {
  return NODE_COLORS[type] ?? "#9CA3AF";
}

export interface ForceNodeData {
  entity: Entity;
  degree: number;
  selected: boolean;
  [key: string]: unknown;
}

const ForceGraphNodeInner: FC<NodeProps<Node<ForceNodeData>>> = ({ data }) => {
  const { entity, degree, selected } = data;
  const color = nodeColor(entity.type);
  const size = Math.max(28, Math.min(56, 28 + Math.log2(1 + degree) * 8));

  return (
    <>
      <Handle type="target" position={Position.Top} style={{ visibility: "hidden" }} />
      <div
        className="flex items-center justify-center rounded-full border-2 text-white text-xs font-bold cursor-pointer shadow-md transition-all hover:scale-110"
        style={{
          width: size,
          height: size,
          backgroundColor: color,
          borderColor: selected ? "#FFFFFF" : color,
          boxShadow: selected
            ? `0 0 0 3px ${color}, 0 0 12px ${color}80`
            : "0 1px 3px rgba(0,0,0,0.2)",
        }}
        title={`${entity.canonical_name} (${entity.type})`}
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

export const ForceGraphNode = memo(ForceGraphNodeInner);
