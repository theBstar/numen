import { useState } from "react";
import {
  ChevronRight,
  ChevronDown,
  Folder,
  FolderOpen,
  FileText,
  Image,
  Plus,
  MoreHorizontal,
  Pencil,
  Trash2,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { getStatusDotColor } from "@/components/prd/PrdStatusBadge";
import { cn } from "@/lib/utils";
import type { PrdTreeNode, PrdNodeType } from "@/types";

interface FolderTreeProps {
  nodes: PrdTreeNode[];
  selectedId?: string;
  onSelect: (node: PrdTreeNode) => void;
  onCreateFolder?: (parentId: string | null) => void;
  onCreateDocument?: (parentId: string | null) => void;
  onDelete?: (nodeId: string) => void;
  onRename?: (nodeId: string) => void;
}

function getNodeIcon(nodeType: PrdNodeType, isOpen: boolean) {
  switch (nodeType) {
    case "folder":
      return isOpen ? FolderOpen : Folder;
    case "image":
      return Image;
    case "document":
    default:
      return FileText;
  }
}

interface TreeNodeItemProps {
  node: PrdTreeNode;
  depth: number;
  selectedId?: string;
  onSelect: (node: PrdTreeNode) => void;
  onCreateFolder?: (parentId: string | null) => void;
  onCreateDocument?: (parentId: string | null) => void;
  onDelete?: (nodeId: string) => void;
  onRename?: (nodeId: string) => void;
}

function TreeNodeItem({
  node,
  depth,
  selectedId,
  onSelect,
  onCreateFolder,
  onCreateDocument,
  onDelete,
  onRename,
}: TreeNodeItemProps) {
  const [expanded, setExpanded] = useState(true);
  const isFolder = node.node_type === "folder";
  const hasChildren = node.children.length > 0;
  const isSelected = selectedId === node.id;
  const Icon = getNodeIcon(node.node_type, expanded);
  const dotColor = getStatusDotColor(node.status);

  return (
    <div>
      <div
        className={cn(
          "group flex items-center gap-1 rounded-md px-1 py-1 text-sm transition-colors",
          isSelected
            ? "bg-primary-50 text-primary-700"
            : "text-surface-700 hover:bg-surface-100",
        )}
        style={{ paddingLeft: `${depth * 16 + 4}px` }}
      >
        {/* Expand/collapse chevron */}
        {isFolder ? (
          <button
            onClick={(e) => {
              e.stopPropagation();
              setExpanded(!expanded);
            }}
            className="flex h-5 w-5 shrink-0 items-center justify-center rounded hover:bg-surface-200"
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : (
          <span className="h-5 w-5 shrink-0" />
        )}

        {/* Node content - clickable */}
        <button
          onClick={() => onSelect(node)}
          className="flex min-w-0 flex-1 items-center gap-1.5"
        >
          <Icon size={14} className="shrink-0 text-surface-400" />
          <span
            className={cn(
              "h-2 w-2 shrink-0 rounded-full",
              dotColor,
            )}
          />
          <span className="truncate">{node.title}</span>
        </button>

        {/* Context menu */}
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              onClick={(e) => e.stopPropagation()}
              className="flex h-5 w-5 shrink-0 items-center justify-center rounded opacity-0 transition-opacity group-hover:opacity-100 hover:bg-surface-200"
            >
              <MoreHorizontal size={14} />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            {isFolder && (
              <>
                <DropdownMenuItem
                  onClick={() => onCreateDocument?.(node.id)}
                >
                  <FileText size={14} className="mr-2" />
                  New Document
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => onCreateFolder?.(node.id)}
                >
                  <Folder size={14} className="mr-2" />
                  New Folder
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}
            <DropdownMenuItem onClick={() => onRename?.(node.id)}>
              <Pencil size={14} className="mr-2" />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onDelete?.(node.id)}>
              <Trash2 size={14} className="mr-2" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
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
              onCreateFolder={onCreateFolder}
              onCreateDocument={onCreateDocument}
              onDelete={onDelete}
              onRename={onRename}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function FolderTree({
  nodes,
  selectedId,
  onSelect,
  onCreateFolder,
  onCreateDocument,
  onDelete,
  onRename,
}: FolderTreeProps) {
  return (
    <div className="space-y-0.5">
      {/* Root actions */}
      <div className="flex items-center justify-between px-2 pb-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-surface-400">
          Documents
        </span>
        <div className="flex items-center gap-1">
          <button
            onClick={() => onCreateDocument?.(null)}
            className="flex h-6 w-6 items-center justify-center rounded hover:bg-surface-200"
            title="New document"
          >
            <Plus size={14} className="text-surface-500" />
          </button>
          <button
            onClick={() => onCreateFolder?.(null)}
            className="flex h-6 w-6 items-center justify-center rounded hover:bg-surface-200"
            title="New folder"
          >
            <Folder size={14} className="text-surface-500" />
          </button>
        </div>
      </div>

      {/* Tree nodes */}
      {nodes.length === 0 ? (
        <p className="px-2 py-4 text-xs text-surface-400">
          No documents yet. Create one to get started.
        </p>
      ) : (
        nodes.map((node) => (
          <TreeNodeItem
            key={node.id}
            node={node}
            depth={0}
            selectedId={selectedId}
            onSelect={onSelect}
            onCreateFolder={onCreateFolder}
            onCreateDocument={onCreateDocument}
            onDelete={onDelete}
            onRename={onRename}
          />
        ))
      )}
    </div>
  );
}
