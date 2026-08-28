import { Link } from "react-router-dom";
import { BookOpen, FileText, ExternalLink } from "lucide-react";
import type { WikiConceptDetail as WikiConceptDetailType } from "@/types";

interface WikiConceptDetailProps {
  concept: WikiConceptDetailType;
}

export function WikiConceptDetail({ concept }: WikiConceptDetailProps) {
  return (
    <div className="px-8 py-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-flex items-center rounded-full bg-orange-50 px-2.5 py-0.5 text-xs font-medium text-orange-700">
            concept
          </span>
        </div>
        <h1 className="text-xl font-semibold text-surface-900">{concept.term}</h1>
      </div>

      {/* Definition */}
      <div className="rounded-lg border border-surface-200 bg-white p-5">
        <p className="text-sm leading-relaxed text-surface-700">
          {concept.definition || "No definition available."}
        </p>
      </div>

      {/* PRD References */}
      {concept.prd_references.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-surface-700">
            <FileText size={14} className="inline mr-1" />
            Defined In
          </h2>
          <div className="space-y-2">
            {concept.prd_references.map((ref, i) => (
              <div
                key={i}
                className="rounded-md border border-surface-200 bg-white p-3"
              >
                <Link
                  to={`/prds/${ref.entity_id}`}
                  className="font-medium text-sm text-primary-600 hover:text-primary-700 hover:underline"
                >
                  {ref.prd_title || "Untitled PRD"}
                  <ExternalLink size={12} className="inline ml-1" />
                </Link>
                {ref.section_slugs.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {ref.section_slugs.map((slug) => (
                      <Link
                        key={slug}
                        to={`/prds/${ref.entity_id}#${slug}`}
                        className="inline-flex items-center rounded bg-surface-100 px-1.5 py-0.5 text-[11px] text-surface-500 hover:bg-surface-200 hover:text-surface-700"
                      >
                        #{slug}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Features that use this concept */}
      {concept.features.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-surface-700">
            <BookOpen size={14} className="inline mr-1" />
            Used In Features
          </h2>
          <div className="space-y-2">
            {concept.features.map((f) => (
              <Link
                key={f.id}
                to={`/wiki/features/${f.slug}`}
                className="flex items-center justify-between rounded-md border border-surface-200 bg-white p-3 transition-colors hover:border-primary-200"
              >
                <div>
                  <span className="font-medium text-sm text-surface-900">{f.title}</span>
                  <p className="mt-0.5 text-xs text-surface-400 line-clamp-1">
                    {f.description}
                  </p>
                </div>
                <span
                  className={`ml-2 inline-block h-2 w-2 shrink-0 rounded-full ${
                    f.status === "active"
                      ? "bg-green-400"
                      : f.status === "planned"
                        ? "bg-amber-400"
                        : "bg-surface-300"
                  }`}
                />
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Metadata */}
      {concept.generated_at && (
        <p className="text-xs text-surface-400">
          Generated {new Date(concept.generated_at).toLocaleDateString()}
        </p>
      )}
    </div>
  );
}
