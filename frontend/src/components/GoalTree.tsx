import { useState } from "react";
import { ChevronRight, ChevronDown } from "lucide-react";
import { GoalCard } from "./GoalCard";
import type { GoalTreeNode } from "@/types";

interface GoalTreeProps {
  goals: GoalTreeNode[];
}

export function GoalTree({ goals }: GoalTreeProps) {
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());

  function toggleCollapse(id: string) {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="space-y-2">
      {goals.map((node) => (
        <GoalTreeNodeComponent
          key={node.id}
          node={node}
          depth={0}
          collapsedIds={collapsedIds}
          onToggle={toggleCollapse}
        />
      ))}
    </div>
  );
}

function GoalTreeNodeComponent({
  node,
  depth,
  collapsedIds,
  onToggle,
}: {
  node: GoalTreeNode;
  depth: number;
  collapsedIds: Set<string>;
  onToggle: (id: string) => void;
}) {
  const isCollapsed = collapsedIds.has(node.id);
  const hasChildren = node.children.length > 0;

  return (
    <div>
      <div
        className="flex items-center gap-2"
        style={{ paddingLeft: `${depth * 32}px` }}
      >
        {hasChildren ? (
          <button
            onClick={() => onToggle(node.id)}
            className="flex h-6 w-6 items-center justify-center rounded text-surface-400 hover:bg-surface-100 hover:text-surface-600"
          >
            {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
          </button>
        ) : (
          <div className="w-6" />
        )}
        <div className="flex-1">
          <GoalCard goal={node} />
        </div>
      </div>

      {hasChildren && !isCollapsed && (
        <div className="mt-2 space-y-2 border-l-2 border-surface-200" style={{ marginLeft: `${depth * 32 + 12}px` }}>
          {node.children.map((child) => (
            <GoalTreeNodeComponent
              key={child.id}
              node={child}
              depth={depth + 1}
              collapsedIds={collapsedIds}
              onToggle={onToggle}
            />
          ))}
        </div>
      )}
    </div>
  );
}
