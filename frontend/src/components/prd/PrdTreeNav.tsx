import { useState, useMemo } from "react";
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FileText,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getStatusDotColor } from "@/components/prd/PrdStatusBadge";
import type { PrdTreeNode, PrdStatus } from "@/types";

interface PrdTreeNavProps {
  nodes: PrdTreeNode[];
  selectedId?: string;
  onSelect: (nodeId: string) => void;
  searchFilter?: string;
  statusFilter?: PrdStatus[];
}

function matchesSearch(node: PrdTreeNode, search: string): boolean {
  const lower = search.toLowerCase();
  if (node.title.toLowerCase().includes(lower)) return true;
  return node.children.some((child) => matchesSearch(child, search));
}

function matchesStatus(node: PrdTreeNode, statusFilter: PrdStatus[]): boolean {
  if (statusFilter.length === 0) return true;
  if (node.node_type === "folder") {
    return node.children.some((child) => matchesStatus(child, statusFilter));
  }
  return statusFilter.includes(node.status);
}

function filterTree(
  nodes: PrdTreeNode[],
  search: string,
  statusFilter: PrdStatus[],
): PrdTreeNode[] {
  return nodes
    .filter((node) => {
      const searchMatch = !search || matchesSearch(node, search);
      const statusMatch = matchesStatus(node, statusFilter);
      return searchMatch && statusMatch;
    })
    .map((node) => ({
      ...node,
      children: filterTree(node.children, search, statusFilter),
    }));
}

interface TreeNodeItemProps {
  node: PrdTreeNode;
  depth: number;
  selectedId?: string;
  onSelect: (nodeId: string) => void;
  forceExpand?: boolean;
}

function TreeNodeItem({ node, depth, selectedId, onSelect, forceExpand }: TreeNodeItemProps) {
  const [expanded, setExpanded] = useState(forceExpand ?? true);
  const isFolder = node.node_type === "folder";
  const hasChildren = node.children.length > 0;
  const isSelected = selectedId === node.id;
  const dotColor = getStatusDotColor(node.status as PrdStatus);

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1 rounded-md px-1 py-1 text-sm transition-colors cursor-pointer",
          isSelected
            ? "bg-primary-50 text-primary-700"
            : "text-surface-700 hover:bg-surface-100",
        )}
        style={{ paddingLeft: `${depth * 14 + 4}px` }}
        onClick={() => {
          if (!isFolder) {
            onSelect(node.id);
          } else if (hasChildren) {
            setExpanded(!expanded);
          }
        }}
      >
        {/* Expand/collapse */}
        {isFolder && hasChildren ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            className="flex h-5 w-5 shrink-0 items-center justify-center rounded hover:bg-surface-200"
          >
            {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        ) : (
          <span className="h-5 w-5 shrink-0" />
        )}

        {/* Icon */}
        {isFolder ? (
          expanded ? (
            <FolderOpen size={13} className="shrink-0 text-surface-400" />
          ) : (
            <Folder size={13} className="shrink-0 text-surface-400" />
          )
        ) : (
          <FileText size={13} className="shrink-0 text-surface-400" />
        )}

        {/* Status dot */}
        {!isFolder && (
          <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dotColor)} />
        )}

        {/* Title */}
        <span className="min-w-0 flex-1 truncate text-xs">{node.title}</span>
      </div>

      {/* Children */}
      {isFolder && expanded && hasChildren && (
        <div>
          {node.children.map((child) => (
            <TreeNodeItem
              key={child.id}
              node={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
              forceExpand={forceExpand}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function PrdTreeNav({
  nodes,
  selectedId,
  onSelect,
  searchFilter,
  statusFilter = [],
}: PrdTreeNavProps) {
  const filteredNodes = useMemo(
    () => filterTree(nodes, searchFilter ?? "", statusFilter),
    [nodes, searchFilter, statusFilter],
  );

  if (filteredNodes.length === 0) {
    return (
      <p className="px-3 py-4 text-xs text-surface-400">
        {searchFilter || statusFilter.length > 0
          ? "No matching PRDs found."
          : "No PRDs yet."}
      </p>
    );
  }

  return (
    <div className="space-y-0.5">
      {filteredNodes.map((node) => (
        <TreeNodeItem
          key={node.id}
          node={node}
          depth={0}
          selectedId={selectedId}
          onSelect={onSelect}
          forceExpand={!!(searchFilter || statusFilter.length > 0)}
        />
      ))}
    </div>
  );
}
