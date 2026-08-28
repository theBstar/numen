import { useState } from "react";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import type { PrdCommentResponse } from "@/types";
import {
  Check,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  MessageSquare,
  Reply,
  Trash2,
  Undo2,
} from "lucide-react";

interface PrdCommentThreadProps {
  prdId: string;
  blockId: string;
  comments: PrdCommentResponse[];
  onAddComment: (content: string, parentId?: string) => void;
  onResolve: (commentId: string) => void;
  onUnresolve: (commentId: string) => void;
  onDelete: (commentId: string) => void;
  currentMemberId?: string;
}

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

function SingleComment({
  comment,
  onReply,
  onResolve,
  onUnresolve,
  onDelete,
  currentMemberId,
  isReply = false,
}: {
  comment: PrdCommentResponse;
  onReply: (commentId: string) => void;
  onResolve: (commentId: string) => void;
  onUnresolve: (commentId: string) => void;
  onDelete: (commentId: string) => void;
  currentMemberId?: string;
  isReply?: boolean;
}) {
  const isOwn = currentMemberId && comment.author_id === currentMemberId;

  return (
    <div className={cn("group flex gap-2", isReply && "ml-8")}>
      <Avatar className="h-6 w-6 shrink-0">
        <AvatarFallback className="bg-primary-100 text-[10px] font-medium text-primary-700">
          {getInitials(comment.author_name)}
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-surface-700">
            {comment.author_name ?? "Unknown"}
          </span>
          <span className="text-[10px] text-surface-400">
            {formatRelativeTime(comment.created_at)}
          </span>
        </div>
        <p className="mt-0.5 whitespace-pre-wrap text-sm text-surface-600">
          {comment.content}
        </p>
        <div className="mt-1 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
          {!isReply && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-[10px] text-surface-400 hover:text-surface-600"
              onClick={() => onReply(comment.id)}
            >
              <Reply className="mr-0.5 h-3 w-3" />
              Reply
            </Button>
          )}
          {!isReply && !comment.is_resolved && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-[10px] text-surface-400 hover:text-emerald-600"
              onClick={() => onResolve(comment.id)}
            >
              <Check className="mr-0.5 h-3 w-3" />
              Resolve
            </Button>
          )}
          {!isReply && comment.is_resolved && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-[10px] text-emerald-500 hover:text-surface-600"
              onClick={() => onUnresolve(comment.id)}
            >
              <Undo2 className="mr-0.5 h-3 w-3" />
              Reopen
            </Button>
          )}
          {isOwn && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 px-1.5 text-[10px] text-surface-400 hover:text-red-500"
              onClick={() => onDelete(comment.id)}
            >
              <Trash2 className="mr-0.5 h-3 w-3" />
              Delete
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

export function PrdCommentThread({
  comments,
  onAddComment,
  onResolve,
  onUnresolve,
  onDelete,
  currentMemberId,
}: PrdCommentThreadProps) {
  const [newComment, setNewComment] = useState("");
  const [replyingTo, setReplyingTo] = useState<string | null>(null);
  const [replyContent, setReplyContent] = useState("");
  const [expandedResolved, setExpandedResolved] = useState<Set<string>>(
    new Set(),
  );

  const handleSubmit = () => {
    const trimmed = newComment.trim();
    if (!trimmed) return;
    onAddComment(trimmed);
    setNewComment("");
  };

  const handleReply = (parentId: string) => {
    const trimmed = replyContent.trim();
    if (!trimmed) return;
    onAddComment(trimmed, parentId);
    setReplyContent("");
    setReplyingTo(null);
  };

  const toggleResolved = (commentId: string) => {
    setExpandedResolved((prev) => {
      const next = new Set(prev);
      if (next.has(commentId)) {
        next.delete(commentId);
      } else {
        next.add(commentId);
      }
      return next;
    });
  };

  const unresolvedComments = comments.filter((c) => !c.is_resolved);
  const resolvedComments = comments.filter((c) => c.is_resolved);

  return (
    <div className="space-y-3">
      {/* Unresolved comments */}
      {unresolvedComments.map((comment) => (
        <div key={comment.id} className="space-y-2">
          <SingleComment
            comment={comment}
            onReply={(id) => setReplyingTo(id)}
            onResolve={onResolve}
            onUnresolve={onUnresolve}
            onDelete={onDelete}
            currentMemberId={currentMemberId}
          />
          {/* Replies */}
          {comment.replies.map((reply) => (
            <SingleComment
              key={reply.id}
              comment={reply}
              onReply={(id) => setReplyingTo(id)}
              onResolve={onResolve}
              onUnresolve={onUnresolve}
              onDelete={onDelete}
              currentMemberId={currentMemberId}
              isReply
            />
          ))}
          {/* Reply input */}
          {replyingTo === comment.id && (
            <div className="ml-8 flex gap-2">
              <Textarea
                value={replyContent}
                onChange={(e) => setReplyContent(e.target.value)}
                placeholder="Write a reply..."
                className="min-h-[40px] flex-1 resize-none text-sm"
                rows={1}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                    handleReply(comment.id);
                  }
                  if (e.key === "Escape") {
                    setReplyingTo(null);
                    setReplyContent("");
                  }
                }}
              />
              <div className="flex flex-col gap-1">
                <Button
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => handleReply(comment.id)}
                  disabled={!replyContent.trim()}
                >
                  Reply
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => {
                    setReplyingTo(null);
                    setReplyContent("");
                  }}
                >
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </div>
      ))}

      {/* Resolved comments */}
      {resolvedComments.length > 0 && (
        <div className="space-y-1">
          {resolvedComments.map((comment) => (
            <div key={comment.id}>
              <button
                type="button"
                className="flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-xs text-surface-400 transition-colors hover:bg-surface-50 hover:text-surface-500"
                onClick={() => toggleResolved(comment.id)}
              >
                {expandedResolved.has(comment.id) ? (
                  <ChevronDown className="h-3 w-3" />
                ) : (
                  <ChevronRight className="h-3 w-3" />
                )}
                <CheckCircle className="h-3 w-3 text-emerald-400" />
                <span className="truncate">
                  {comment.author_name ?? "Unknown"}: {comment.content}
                </span>
                <span className="ml-auto shrink-0 text-[10px]">(resolved)</span>
              </button>
              {expandedResolved.has(comment.id) && (
                <div className="mt-1 space-y-2 rounded-md border border-surface-100 bg-surface-50 p-2">
                  <SingleComment
                    comment={comment}
                    onReply={(id) => setReplyingTo(id)}
                    onResolve={onResolve}
                    onUnresolve={onUnresolve}
                    onDelete={onDelete}
                    currentMemberId={currentMemberId}
                  />
                  {comment.replies.map((reply) => (
                    <SingleComment
                      key={reply.id}
                      comment={reply}
                      onReply={(id) => setReplyingTo(id)}
                      onResolve={onResolve}
                      onUnresolve={onUnresolve}
                      onDelete={onDelete}
                      currentMemberId={currentMemberId}
                      isReply
                    />
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* New comment input */}
      <div className="flex gap-2">
        <Textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment..."
          className="min-h-[40px] flex-1 resize-none text-sm"
          rows={1}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              handleSubmit();
            }
          }}
        />
        <Button
          size="sm"
          className="h-9 self-end"
          onClick={handleSubmit}
          disabled={!newComment.trim()}
        >
          <MessageSquare className="mr-1 h-3.5 w-3.5" />
          Send
        </Button>
      </div>
    </div>
  );
}
