import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useOrgContext } from "@/contexts/OrgContext";
import { useMembers } from "@/hooks/queries";
import {
  usePrdReviews,
  usePrdReviewSummary,
} from "@/hooks/prdQueries";
import {
  useAddReviewer,
  useRemoveReviewer,
  useSubmitReview,
} from "@/hooks/prdMutations";
import type { PrdStatus, PrdReviewStatus, OrgMember } from "@/types";
import {
  Check,
  Clock,
  AlertTriangle,
  Plus,
  X,
  UserCheck,
} from "lucide-react";

interface PrdReviewPanelProps {
  prdId: string;
  currentStatus: PrdStatus;
  isOwner: boolean;
}

const REVIEW_STATUS_CONFIG: Record<
  PrdReviewStatus,
  { icon: typeof Check; label: string; color: string }
> = {
  pending: {
    icon: Clock,
    label: "Pending",
    color: "text-surface-400",
  },
  approved: {
    icon: Check,
    label: "Approved",
    color: "text-emerald-600",
  },
  changes_requested: {
    icon: AlertTriangle,
    label: "Changes Requested",
    color: "text-amber-600",
  },
};

function MemberSearchDropdown({
  onSelect,
  onClose,
  existingMemberIds,
}: {
  onSelect: (memberId: string) => void;
  onClose: () => void;
  existingMemberIds: Set<string>;
}) {
  const [search, setSearch] = useState("");
  const { data: members } = useMembers();

  const filteredMembers = (members ?? []).filter((m: OrgMember) => {
    if (existingMemberIds.has(m.id)) return false;
    const query = search.toLowerCase();
    if (!query) return true;
    return (
      (m.display_name ?? "").toLowerCase().includes(query) ||
      m.email.toLowerCase().includes(query)
    );
  });

  return (
    <div className="absolute left-0 top-full z-10 mt-1 w-64 rounded-md border border-surface-200 bg-white shadow-lg">
      <div className="p-2">
        <input
          autoFocus
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search members..."
          className="w-full rounded-md border border-surface-200 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
          }}
        />
      </div>
      <div className="max-h-48 overflow-y-auto">
        {filteredMembers.length === 0 ? (
          <p className="px-3 py-2 text-xs text-surface-400">No members found</p>
        ) : (
          filteredMembers.map((m: OrgMember) => (
            <button
              key={m.id}
              type="button"
              onClick={() => {
                onSelect(m.id);
                onClose();
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-surface-50"
            >
              <div className="flex h-6 w-6 items-center justify-center rounded-full bg-surface-100 text-xs font-medium text-surface-600">
                {(m.display_name ?? m.email)[0]?.toUpperCase()}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-surface-700">
                  {m.display_name ?? m.email.split("@")[0]}
                </p>
                <p className="truncate text-xs text-surface-400">{m.email}</p>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

export function PrdReviewPanel({
  prdId,
  currentStatus: _currentStatus,
  isOwner,
}: PrdReviewPanelProps) {
  // _currentStatus available for future status-dependent UI (e.g. disabling actions)
  void _currentStatus;
  const { memberId } = useOrgContext();
  const { data: reviewsData } = usePrdReviews(prdId);
  const { data: summary } = usePrdReviewSummary(prdId);
  const addReviewer = useAddReviewer(prdId);
  const removeReviewer = useRemoveReviewer(prdId);
  const submitReview = useSubmitReview(prdId);

  const [showAddDropdown, setShowAddDropdown] = useState(false);
  const [showReviewForm, setShowReviewForm] = useState(false);
  const [reviewComment, setReviewComment] = useState("");
  const [reviewDecision, setReviewDecision] = useState<PrdReviewStatus | null>(null);

  const reviews = reviewsData?.items ?? [];

  // Check if the current user is a reviewer
  const isReviewer = reviews.some(
    (r) => r.reviewer_id === memberId && r.status === "pending",
  );

  // Build set of existing reviewer member IDs from reviews
  const existingReviewerIds = new Set(
    reviews.map((r) => r.reviewer_id),
  );

  const handleSubmitReview = () => {
    if (!reviewDecision) return;
    submitReview.mutate(
      {
        status: reviewDecision,
        comment: reviewComment || null,
      },
      {
        onSuccess: () => {
          setShowReviewForm(false);
          setReviewComment("");
          setReviewDecision(null);
        },
      },
    );
  };

  return (
    <div className="space-y-3">
      {/* Review summary */}
      {summary && summary.total_reviewers > 0 && (
        <div className="rounded-md bg-surface-50 p-2.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-surface-500">
              Reviews
            </span>
            {summary.can_approve ? (
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
                All approved
              </span>
            ) : (
              <span className="text-xs text-surface-400">
                {summary.approved_count}/{summary.total_reviewers} approved
              </span>
            )}
          </div>
          {summary.pending_count > 0 && (
            <p className="mt-1 text-xs text-surface-400">
              {summary.pending_count} pending
            </p>
          )}
          {summary.changes_requested_count > 0 && (
            <p className="mt-1 text-xs text-amber-600">
              {summary.changes_requested_count} requested changes
            </p>
          )}
        </div>
      )}

      {/* Reviewer list */}
      <div className="space-y-1.5">
        {reviews.map((review) => {
          const config = REVIEW_STATUS_CONFIG[review.status];
          const Icon = config.icon;

          return (
            <div
              key={review.id}
              className="flex items-center justify-between rounded-md px-2 py-1.5 transition-colors hover:bg-surface-50"
            >
              <div className="flex items-center gap-2">
                <Icon className={cn("h-3.5 w-3.5", config.color)} />
                <span className="text-sm text-surface-700">
                  {review.reviewer_name ?? "Unknown"}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <span className={cn("text-xs", config.color)}>
                  {config.label}
                </span>
                {isOwner && (
                  <button
                    type="button"
                    onClick={() => removeReviewer.mutate(review.reviewer_id)}
                    className="rounded p-0.5 text-surface-300 transition-colors hover:bg-surface-100 hover:text-surface-500"
                    title="Remove reviewer"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Add reviewer button */}
      {isOwner && (
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowAddDropdown(!showAddDropdown)}
            className="inline-flex items-center gap-1 rounded-md border border-dashed border-surface-300 px-2 py-1 text-xs text-surface-400 transition-colors hover:border-surface-400 hover:text-surface-500"
          >
            <Plus className="h-3 w-3" />
            Add Reviewer
          </button>
          {showAddDropdown && (
            <MemberSearchDropdown
              onSelect={(id) => addReviewer.mutate(id)}
              onClose={() => setShowAddDropdown(false)}
              existingMemberIds={existingReviewerIds}
            />
          )}
        </div>
      )}

      {/* Submit review form (for current user if they are a reviewer) */}
      {isReviewer && !showReviewForm && (
        <Button
          variant="outline"
          size="sm"
          className="w-full gap-1.5"
          onClick={() => setShowReviewForm(true)}
        >
          <UserCheck className="h-3.5 w-3.5" />
          Submit Review
        </Button>
      )}

      {showReviewForm && (
        <div className="space-y-2 rounded-md border border-surface-200 p-3">
          <p className="text-xs font-medium text-surface-500">Your Review</p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setReviewDecision("approved")}
              className={cn(
                "flex-1 rounded-md border px-2 py-1.5 text-xs font-medium transition-colors",
                reviewDecision === "approved"
                  ? "border-emerald-500 bg-emerald-50 text-emerald-700"
                  : "border-surface-200 text-surface-600 hover:border-emerald-300",
              )}
            >
              <Check className="mr-1 inline h-3 w-3" />
              Approve
            </button>
            <button
              type="button"
              onClick={() => setReviewDecision("changes_requested")}
              className={cn(
                "flex-1 rounded-md border px-2 py-1.5 text-xs font-medium transition-colors",
                reviewDecision === "changes_requested"
                  ? "border-amber-500 bg-amber-50 text-amber-700"
                  : "border-surface-200 text-surface-600 hover:border-amber-300",
              )}
            >
              <AlertTriangle className="mr-1 inline h-3 w-3" />
              Request Changes
            </button>
          </div>
          <Textarea
            value={reviewComment}
            onChange={(e) => setReviewComment(e.target.value)}
            placeholder="Optional comment..."
            className="min-h-[60px] text-sm"
          />
          <div className="flex justify-end gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setShowReviewForm(false);
                setReviewComment("");
                setReviewDecision(null);
              }}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={!reviewDecision || submitReview.isPending}
              onClick={handleSubmitReview}
            >
              Submit
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
