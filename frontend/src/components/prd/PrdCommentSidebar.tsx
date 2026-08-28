import { useState, useMemo } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import type { PrdCommentResponse } from "@/types";
import { usePrdComments } from "@/hooks/prdQueries";
import {
  useResolveComment,
} from "@/hooks/prdMutations";
import {
  CheckCircle,
  MessageSquare,
  X,
} from "lucide-react";

interface PrdCommentSidebarProps {
  prdId: string;
  open: boolean;
  onClose: () => void;
  onScrollToBlock?: (blockId: string) => void;
}

type FilterTab = "all" | "open" | "resolved";

function getInitials(name: string | null): string {
  if (!name) return "?";
  return name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

function formatRelativeTime(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/**
 * Group comments by block_id for display in the sidebar.
 * Comments without a block_id go into a "Document-level" group.
 */
function groupByBlock(
  comments: PrdCommentResponse[],
): { blockId: string | null; label: string; comments: PrdCommentResponse[] }[] {
  const groups = new Map<string | null, PrdCommentResponse[]>();

  for (const comment of comments) {
    const key = comment.block_id;
    const existing = groups.get(key) ?? [];
    existing.push(comment);
    groups.set(key, existing);
  }

  const result: { blockId: string | null; label: string; comments: PrdCommentResponse[] }[] = [];

  // Document-level comments first
  const docLevel = groups.get(null);
  if (docLevel && docLevel.length > 0) {
    result.push({ blockId: null, label: "Document-level", comments: docLevel });
  }

  // Block-level comments
  for (const [blockId, blockComments] of groups.entries()) {
    if (blockId !== null) {
      result.push({
        blockId,
        label: `Block`,
        comments: blockComments,
      });
    }
  }

  return result;
}

export function PrdCommentSidebar({
  prdId,
  open,
  onClose,
  onScrollToBlock,
}: PrdCommentSidebarProps) {
  const [filter, setFilter] = useState<FilterTab>("all");

  const { data } = usePrdComments(prdId);
  const resolveComment = useResolveComment(prdId);

  const allComments = data?.items ?? [];

  const filteredComments = useMemo(() => {
    switch (filter) {
      case "open":
        return allComments.filter((c) => !c.is_resolved);
      case "resolved":
        return allComments.filter((c) => c.is_resolved);
      default:
        return allComments;
    }
  }, [allComments, filter]);

  const openCount = allComments.filter((c) => !c.is_resolved).length;
  const resolvedCount = allComments.filter((c) => c.is_resolved).length;

  const grouped = useMemo(() => groupByBlock(filteredComments), [filteredComments]);

  if (!open) return null;

  return (
    <div className="flex h-full w-80 shrink-0 flex-col border-l border-surface-200 bg-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-surface-200 px-4 py-3">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-surface-500" />
          <h3 className="text-sm font-semibold text-surface-800">Comments</h3>
          {allComments.length > 0 && (
            <Badge variant="secondary" className="h-5 text-[10px]">
              {allComments.length}
            </Badge>
          )}
        </div>
        <Button variant="ghost" size="sm" className="h-7 w-7 p-0" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Filter tabs */}
      <div className="border-b border-surface-200 px-4 py-2">
        <Tabs value={filter} onValueChange={(v) => setFilter(v as FilterTab)}>
          <TabsList className="h-8 w-full">
            <TabsTrigger value="all" className="flex-1 text-xs">
              All ({allComments.length})
            </TabsTrigger>
            <TabsTrigger value="open" className="flex-1 text-xs">
              Open ({openCount})
            </TabsTrigger>
            <TabsTrigger value="resolved" className="flex-1 text-xs">
              Resolved ({resolvedCount})
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Comment list */}
      <ScrollArea className="flex-1">
        <div className="space-y-4 p-4">
          {grouped.length === 0 && (
            <div className="py-8 text-center">
              <MessageSquare className="mx-auto h-8 w-8 text-surface-300" />
              <p className="mt-2 text-sm text-surface-400">No comments yet</p>
              <p className="text-xs text-surface-300">
                Select a block or add a document-level comment
              </p>
            </div>
          )}

          {grouped.map((group) => (
            <div key={group.blockId ?? "doc"} className="space-y-2">
              {/* Section header */}
              <button
                type="button"
                className={cn(
                  "flex w-full items-center gap-1.5 rounded px-2 py-1 text-xs font-medium text-surface-500",
                  group.blockId && "cursor-pointer hover:bg-surface-50 hover:text-primary-600",
                  !group.blockId && "cursor-default",
                )}
                onClick={() => {
                  if (group.blockId && onScrollToBlock) {
                    onScrollToBlock(group.blockId);
                  }
                }}
              >
                {group.label}
                <span className="ml-auto text-[10px] text-surface-300">
                  {group.comments.length} comment{group.comments.length !== 1 ? "s" : ""}
                </span>
              </button>

              {/* Comments in this group */}
              {group.comments.map((comment) => (
                <div
                  key={comment.id}
                  className="rounded-lg border border-surface-100 p-3"
                >
                  {/* Comment header */}
                  <div className="mb-1.5 flex items-center gap-2">
                    <Avatar className="h-5 w-5">
                      <AvatarFallback className="bg-primary-100 text-[8px] font-medium text-primary-700">
                        {getInitials(comment.author_name)}
                      </AvatarFallback>
                    </Avatar>
                    <span className="text-xs font-medium text-surface-700">
                      {comment.author_name ?? "Unknown"}
                    </span>
                    <span className="text-[10px] text-surface-400">
                      {formatRelativeTime(comment.created_at)}
                    </span>
                    {comment.is_resolved && (
                      <CheckCircle className="ml-auto h-3.5 w-3.5 text-emerald-400" />
                    )}
                  </div>

                  {/* Comment body */}
                  <p className="text-sm text-surface-600 line-clamp-3">
                    {comment.content}
                  </p>

                  {/* Reply count */}
                  {comment.replies.length > 0 && (
                    <p className="mt-1.5 text-[10px] text-surface-400">
                      {comment.replies.length} repl{comment.replies.length === 1 ? "y" : "ies"}
                    </p>
                  )}

                  {/* Quick actions */}
                  <div className="mt-2 flex items-center gap-1">
                    {!comment.is_resolved && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-1.5 text-[10px] text-surface-400 hover:text-emerald-600"
                        onClick={() =>
                          resolveComment.mutate({ commentId: comment.id, resolve: true })
                        }
                      >
                        Resolve
                      </Button>
                    )}
                    {comment.is_resolved && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-1.5 text-[10px] text-emerald-500 hover:text-surface-600"
                        onClick={() =>
                          resolveComment.mutate({ commentId: comment.id, resolve: false })
                        }
                      >
                        Reopen
                      </Button>
                    )}
                    {group.blockId && onScrollToBlock && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-6 px-1.5 text-[10px] text-surface-400 hover:text-primary-600"
                        onClick={() => onScrollToBlock(group.blockId!)}
                      >
                        Go to block
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
