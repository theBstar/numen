import { Link } from "react-router-dom";
import {
  BookOpen,
  Sparkles,
  Loader2,
  RefreshCw,
  Layers,
  Tag,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type { WikiProductSummary, WikiFeatureListItem, WikiStats } from "@/types";

interface WikiLandingProps {
  summary: WikiProductSummary;
  features: WikiFeatureListItem[];
  stats: WikiStats;
  isGenerating: boolean;
  onGenerate: () => void;
}

export function WikiLanding({
  summary,
  features,
  stats,
  isGenerating,
  onGenerate,
}: WikiLandingProps) {
  const hasContent = features.length > 0 || summary.summary;

  return (
    <div className="px-8 py-6 max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-surface-900">
            <BookOpen size={24} className="text-primary-500" />
            Product Wiki
          </h1>
          <p className="mt-1 text-sm text-surface-500">
            Features and concepts extracted from your PRDs
          </p>
        </div>
        <Button
          onClick={onGenerate}
          disabled={isGenerating}
          variant="outline"
          size="sm"
          className="gap-1.5"
        >
          {isGenerating ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <RefreshCw size={14} />
          )}
          {hasContent ? "Regenerate" : "Generate Wiki"}
        </Button>
      </div>

      {/* Product Summary */}
      {summary.summary ? (
        <div className="rounded-lg border border-primary-100 bg-primary-50/50 p-5">
          <div className="flex items-center gap-2 mb-2">
            <Sparkles size={16} className="text-primary-500" />
            <h2 className="text-sm font-semibold text-primary-700">Product Summary</h2>
          </div>
          <p className="text-sm leading-relaxed text-surface-700">{summary.summary}</p>
          <div className="mt-3 flex gap-4 text-xs text-surface-400">
            <span>{summary.feature_count} features</span>
            <span>{summary.prd_count} PRDs analyzed</span>
            {summary.generated_at && (
              <span>Generated {new Date(summary.generated_at).toLocaleDateString()}</span>
            )}
          </div>
        </div>
      ) : !isGenerating ? (
        <div className="rounded-lg border border-dashed border-surface-200 bg-surface-50 p-8 text-center">
          <BookOpen size={32} className="mx-auto mb-3 text-surface-300" />
          <p className="text-sm text-surface-500">
            No wiki content yet. Click "Generate Wiki" to extract features from your PRDs.
          </p>
        </div>
      ) : null}

      {/* Stats bar */}
      {hasContent && (
        <div className="flex gap-6 text-sm">
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full bg-green-400" />
            <span className="text-surface-600">{stats.active} active</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="h-2 w-2 rounded-full bg-amber-400" />
            <span className="text-surface-600">{stats.planned} planned</span>
          </div>
          {stats.manual_edits > 0 && (
            <div className="flex items-center gap-1.5">
              <Tag size={12} className="text-surface-400" />
              <span className="text-surface-600">{stats.manual_edits} manual edits</span>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <Sparkles size={12} className="text-surface-400" />
            <span className="text-surface-600">{stats.concept_count} concepts</span>
          </div>
        </div>
      )}

      {/* Feature Cards */}
      {features.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          {features.map((f) => (
            <Link
              key={f.id}
              to={`/wiki/features/${f.slug}`}
              className="group rounded-lg border border-surface-200 bg-white p-4 transition-all hover:border-primary-200 hover:shadow-sm"
            >
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-medium text-surface-900 group-hover:text-primary-700">
                  {f.title}
                </h3>
                <div className="flex shrink-0 items-center gap-1.5">
                  {f.is_manual && <Tag size={12} className="text-surface-400" />}
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${
                      f.status === "active"
                        ? "bg-green-400"
                        : f.status === "planned"
                          ? "bg-amber-400"
                          : "bg-surface-300"
                    }`}
                  />
                </div>
              </div>
              <p className="mt-1.5 text-sm leading-relaxed text-surface-500 line-clamp-2">
                {f.description}
              </p>
              <div className="mt-3 flex items-center gap-3 text-xs text-surface-400">
                {f.domain_group && (
                  <span className="flex items-center gap-1">
                    <Layers size={10} />
                    {f.domain_group}
                  </span>
                )}
                <span>{f.prd_count} PRD{f.prd_count !== 1 ? "s" : ""}</span>
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Generating indicator */}
      {isGenerating && (
        <div className="flex items-center justify-center py-8 text-surface-400">
          <Loader2 size={20} className="animate-spin mr-2" />
          <span className="text-sm">Generating wiki from PRDs...</span>
        </div>
      )}
    </div>
  );
}
