import { useState, useCallback } from "react";
import { Link } from "react-router-dom";
import {
  ChevronDown,
  ChevronUp,
  Users,
  Sparkles,
  AlertTriangle,
  GitPullRequest,
  ArrowRight,
  Check,
  X,
  RefreshCw,
} from "lucide-react";
import { useLinkSuggestions } from "@/hooks/queries";
import {
  getPersonResolutionCount,
  acceptSuggestion,
  dismissSuggestion,
  generateSuggestions,
} from "@/services/api";
import { useOrgContext } from "@/contexts/OrgContext";
import type { LinkSuggestion } from "@/types";
import { useEffect } from "react";

export function ActionsCollapsed() {
  const { orgId } = useOrgContext();
  const [expanded, setExpanded] = useState(false);
  const [pendingResolutions, setPendingResolutions] = useState(0);
  const [resolutionsLoading, setResolutionsLoading] = useState(true);
  const [generatingSuggestions, setGeneratingSuggestions] = useState(false);
  const [actingSuggestion, setActingSuggestion] = useState<string | null>(null);
  const { data: suggestions, refetch: refetchSuggestions } = useLinkSuggestions("pending", 3);

  const totalBadge = pendingResolutions + (suggestions?.length ?? 0);

  useEffect(() => {
    if (!orgId) return;
    getPersonResolutionCount()
      .then((r) => setPendingResolutions(r.pending))
      .catch(() => setPendingResolutions(0))
      .finally(() => setResolutionsLoading(false));
  }, [orgId]);

  async function handleGenerateSuggestions() {
    setGeneratingSuggestions(true);
    try {
      await generateSuggestions();
      refetchSuggestions();
    } catch (err) {
      console.error("Failed to generate suggestions:", err);
    } finally {
      setGeneratingSuggestions(false);
    }
  }

  const handleAccept = useCallback(async (id: string) => {
    setActingSuggestion(id);
    try {
      await acceptSuggestion(id);
      refetchSuggestions();
    } catch (err) {
      console.error("Failed to accept suggestion:", err);
    } finally {
      setActingSuggestion(null);
    }
  }, [refetchSuggestions]);

  const handleDismiss = useCallback(async (id: string) => {
    setActingSuggestion(id);
    try {
      await dismissSuggestion(id);
      refetchSuggestions();
    } catch (err) {
      console.error("Failed to dismiss suggestion:", err);
    } finally {
      setActingSuggestion(null);
    }
  }, [refetchSuggestions]);

  if (resolutionsLoading) return null;
  if (totalBadge === 0) return null;

  return (
    <div className="card">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between text-left"
      >
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-amber-500" />
          <span className="text-sm font-semibold text-surface-700">Actions</span>
          {totalBadge > 0 && (
            <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-bold text-amber-700">
              {totalBadge}
            </span>
          )}
        </div>
        {expanded ? <ChevronUp size={14} className="text-surface-400" /> : <ChevronDown size={14} className="text-surface-400" />}
      </button>

      {expanded && (
        <div className="mt-3 space-y-3">
          {/* People to Review */}
          {pendingResolutions > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <Users size={12} className="text-surface-400" />
                <span className="text-xs font-medium text-surface-600">People to Review</span>
              </div>
              <Link
                to="/people/resolutions"
                className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs hover:bg-amber-100 transition-colors"
              >
                <div className="flex items-center gap-2 text-amber-800">
                  <AlertTriangle size={12} className="text-amber-600" />
                  <span>
                    <strong>{pendingResolutions}</strong> potential{" "}
                    {pendingResolutions === 1 ? "duplicate" : "duplicates"}
                  </span>
                </div>
                <ArrowRight size={12} className="text-amber-600" />
              </Link>
            </div>
          )}

          {/* AI Link Suggestions */}
          {(suggestions ?? []).length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <GitPullRequest size={12} className="text-surface-400" />
                  <span className="text-xs font-medium text-surface-600">Link Suggestions</span>
                </div>
                <button
                  onClick={handleGenerateSuggestions}
                  disabled={generatingSuggestions}
                  className="text-surface-400 hover:text-primary-600 disabled:opacity-50"
                >
                  <RefreshCw size={10} className={generatingSuggestions ? "animate-spin" : ""} />
                </button>
              </div>
              <div className="space-y-1.5">
                {(suggestions ?? []).map((s: LinkSuggestion) => (
                  <div key={s.id} className="rounded-lg border border-surface-200 px-2.5 py-1.5 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium text-surface-700 truncate">{s.source_entity.canonical_name}</span>
                      <span className="text-[10px] text-surface-400">{Math.round(s.confidence * 100)}%</span>
                    </div>
                    <div className="flex items-center gap-1 text-surface-500 mt-0.5">
                      <ArrowRight size={8} />
                      <span className="truncate">{s.target_entity.canonical_name}</span>
                    </div>
                    <div className="flex gap-1 mt-1.5 justify-end">
                      <button
                        onClick={() => handleAccept(s.id)}
                        disabled={actingSuggestion === s.id}
                        className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-green-50 text-green-700 hover:bg-green-100 disabled:opacity-50 text-[10px]"
                      >
                        <Check size={8} /> Link
                      </button>
                      <button
                        onClick={() => handleDismiss(s.id)}
                        disabled={actingSuggestion === s.id}
                        className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-surface-50 text-surface-500 hover:bg-surface-100 disabled:opacity-50 text-[10px]"
                      >
                        <X size={8} /> Skip
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
