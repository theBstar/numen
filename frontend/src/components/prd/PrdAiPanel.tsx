import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  useAiEditSection,
} from "@/hooks/prdMutations";
import { useAiSuggestedReviewers } from "@/hooks/prdQueries";
import { useAddReviewer } from "@/hooks/prdMutations";
import { PrdAiCompleteDialog } from "./PrdAiCompleteDialog";
import type { AiCompletedBlock, AiSuggestedReviewer } from "@/types";
import {
  Sparkles,
  Pencil,
  UserCheck,
  Loader2,
  ChevronDown,
  ChevronUp,
  Plus,
  Check,
} from "lucide-react";

interface PrdAiPanelProps {
  prdId: string;
  editor: { getJSON: () => Record<string, unknown> } | null;
  selectedBlockIds?: string[];
  onBlocksGenerated: (blocks: AiCompletedBlock[]) => void;
}

export function PrdAiPanel({
  prdId,
  editor: _editor,
  selectedBlockIds = [],
  onBlocksGenerated,
}: PrdAiPanelProps) {
  const [showCompleteDialog, setShowCompleteDialog] = useState(false);
  const [showEditInput, setShowEditInput] = useState(false);
  const [editInstruction, setEditInstruction] = useState("");
  const [showReviewers, setShowReviewers] = useState(false);
  const [addedReviewerIds, setAddedReviewerIds] = useState<Set<string>>(new Set());

  const editMutation = useAiEditSection(prdId);
  const addReviewerMutation = useAddReviewer(prdId);

  const {
    data: reviewersData,
    isLoading: reviewersLoading,
    refetch: refetchReviewers,
  } = useAiSuggestedReviewers(showReviewers ? prdId : undefined);

  const handleEditSection = async () => {
    if (!editInstruction.trim() || selectedBlockIds.length === 0) return;

    try {
      const result = await editMutation.mutateAsync({
        blockIds: selectedBlockIds,
        instruction: editInstruction.trim(),
      });
      onBlocksGenerated(result.items);
      setEditInstruction("");
      setShowEditInput(false);
    } catch {
      // Error handled by mutation state
    }
  };

  const handleAddReviewer = async (memberId: string) => {
    try {
      await addReviewerMutation.mutateAsync(memberId);
      setAddedReviewerIds((prev) => new Set([...prev, memberId]));
    } catch {
      // Error handled by mutation state
    }
  };

  const handleToggleReviewers = () => {
    if (!showReviewers) {
      setShowReviewers(true);
      refetchReviewers();
    } else {
      setShowReviewers(false);
    }
  };

  const suggestedReviewers: AiSuggestedReviewer[] = reviewersData?.items ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-surface-600">
        <Sparkles className="h-4 w-4" />
        <span>AI Assist</span>
      </div>

      {/* AI Complete */}
      <Button
        variant="outline"
        size="sm"
        className="w-full justify-start gap-2"
        onClick={() => setShowCompleteDialog(true)}
      >
        <Sparkles className="h-3.5 w-3.5" />
        AI Complete
      </Button>

      {/* Edit Section */}
      <div className="space-y-2">
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start gap-2"
          disabled={selectedBlockIds.length === 0}
          onClick={() => setShowEditInput(!showEditInput)}
        >
          <Pencil className="h-3.5 w-3.5" />
          Edit Section
          {selectedBlockIds.length === 0 && (
            <span className="ml-auto text-xs text-surface-400">Select blocks first</span>
          )}
        </Button>

        {showEditInput && selectedBlockIds.length > 0 && (
          <div className="space-y-2">
            <Textarea
              placeholder="Describe what to change..."
              value={editInstruction}
              onChange={(e) => setEditInstruction(e.target.value)}
              rows={3}
              className="text-sm"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                onClick={handleEditSection}
                disabled={!editInstruction.trim() || editMutation.isPending}
                className="flex-1"
              >
                {editMutation.isPending ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Editing...
                  </>
                ) : (
                  "Apply Edit"
                )}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setShowEditInput(false);
                  setEditInstruction("");
                }}
              >
                Cancel
              </Button>
            </div>
            {editMutation.isError && (
              <p className="text-xs text-red-600">
                Failed to edit section. Please try again.
              </p>
            )}
          </div>
        )}
      </div>

      {/* Suggest Reviewers */}
      <div className="space-y-2">
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-between gap-2"
          onClick={handleToggleReviewers}
        >
          <span className="flex items-center gap-2">
            <UserCheck className="h-3.5 w-3.5" />
            Suggest Reviewers
          </span>
          {showReviewers ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </Button>

        {showReviewers && (
          <div className="rounded-md border border-surface-200 bg-surface-50 p-2">
            {reviewersLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-4 w-4 animate-spin text-surface-400" />
                <span className="ml-2 text-sm text-surface-500">Finding reviewers...</span>
              </div>
            ) : suggestedReviewers.length === 0 ? (
              <p className="py-3 text-center text-sm text-surface-500">
                No reviewer suggestions available
              </p>
            ) : (
              <ul className="space-y-2">
                {suggestedReviewers.map((reviewer) => {
                  const isAdded = addedReviewerIds.has(reviewer.member_id);
                  return (
                    <li
                      key={reviewer.member_id}
                      className="flex items-start gap-2 rounded-md p-2 hover:bg-surface-100"
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-surface-900">
                          {reviewer.person_name}
                        </p>
                        <p className="text-xs text-surface-500">{reviewer.reason}</p>
                        <div className="mt-0.5 flex items-center gap-1">
                          <div
                            className={cn(
                              "h-1.5 rounded-full",
                              reviewer.score >= 5
                                ? "bg-emerald-500"
                                : reviewer.score >= 3
                                  ? "bg-amber-500"
                                  : "bg-surface-300",
                            )}
                            style={{ width: `${Math.min(reviewer.score * 10, 100)}%`, maxWidth: "60px" }}
                          />
                          <span className="text-xs text-surface-400">
                            {reviewer.score.toFixed(1)}
                          </span>
                        </div>
                      </div>
                      <Button
                        size="sm"
                        variant={isAdded ? "ghost" : "outline"}
                        className="shrink-0"
                        disabled={isAdded || addReviewerMutation.isPending}
                        onClick={() => handleAddReviewer(reviewer.member_id)}
                      >
                        {isAdded ? (
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                        ) : (
                          <Plus className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        )}
      </div>

      {/* AI Complete Dialog */}
      <PrdAiCompleteDialog
        open={showCompleteDialog}
        onClose={() => setShowCompleteDialog(false)}
        prdId={prdId}
        onComplete={onBlocksGenerated}
      />
    </div>
  );
}
