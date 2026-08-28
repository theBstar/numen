import { useState } from "react";
import { Link } from "react-router-dom";
import {
  FileText,
  Users,
  GitPullRequest,
  CheckSquare,
  Pencil,
  Save,
  X,
  Tag,
  ExternalLink,
  Layers,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { linkifyConcepts } from "@/lib/linkifyConcepts";
import type { WikiFeatureDetail as WikiFeatureDetailType, WikiFeatureUpdateRequest } from "@/types";

interface WikiFeatureDetailProps {
  feature: WikiFeatureDetailType;
  onUpdate: (data: WikiFeatureUpdateRequest) => void;
  isUpdating: boolean;
}

export function WikiFeatureDetail({
  feature,
  onUpdate,
  isUpdating,
}: WikiFeatureDetailProps) {
  const [editing, setEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(feature.title);
  const [editDescription, setEditDescription] = useState(feature.description);
  const [editDomainGroup, setEditDomainGroup] = useState(feature.domain_group);

  const handleSave = () => {
    onUpdate({
      title: editTitle,
      description: editDescription,
      domain_group: editDomainGroup,
    });
    setEditing(false);
  };

  const handleCancel = () => {
    setEditTitle(feature.title);
    setEditDescription(feature.description);
    setEditDomainGroup(feature.domain_group);
    setEditing(false);
  };

  const impl = feature.implementation;
  const hasPeople = impl?.people?.length > 0;
  const hasTasks = impl?.tasks?.length > 0;
  const hasPrs = impl?.prs?.length > 0;

  return (
    <div className="px-8 py-6 max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1">
          {editing ? (
            <input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="w-full rounded-md border border-surface-200 px-3 py-2 text-xl font-semibold text-surface-900 focus:border-primary-300 focus:outline-none focus:ring-1 focus:ring-primary-300"
            />
          ) : (
            <h1 className="text-xl font-semibold text-surface-900">{feature.title}</h1>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                feature.status === "active"
                  ? "bg-green-50 text-green-700"
                  : feature.status === "planned"
                    ? "bg-amber-50 text-amber-700"
                    : "bg-surface-100 text-surface-500"
              }`}
            >
              {feature.status}
            </span>
            {feature.domain_group && !editing && (
              <span className="inline-flex items-center gap-1 rounded-full bg-surface-100 px-2 py-0.5 text-xs text-surface-500">
                <Layers size={10} />
                {feature.domain_group}
              </span>
            )}
            {feature.is_manual && (
              <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-600">
                <Tag size={10} />
                manually edited
              </span>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          {editing ? (
            <>
              <Button onClick={handleSave} disabled={isUpdating} size="sm" className="gap-1">
                <Save size={14} />
                Save
              </Button>
              <Button onClick={handleCancel} variant="outline" size="sm" className="gap-1">
                <X size={14} />
                Cancel
              </Button>
            </>
          ) : (
            <Button onClick={() => setEditing(true)} variant="outline" size="sm" className="gap-1">
              <Pencil size={14} />
              Edit
            </Button>
          )}
        </div>
      </div>

      {/* Domain group edit */}
      {editing && (
        <div>
          <label className="text-xs font-medium text-surface-500">Domain Group</label>
          <input
            value={editDomainGroup}
            onChange={(e) => setEditDomainGroup(e.target.value)}
            placeholder="e.g., core, notifications"
            className="mt-1 w-full rounded-md border border-surface-200 px-3 py-1.5 text-sm text-surface-800 focus:border-primary-300 focus:outline-none focus:ring-1 focus:ring-primary-300"
          />
        </div>
      )}

      {/* Description */}
      <div className="rounded-lg border border-surface-200 bg-white p-5">
        {editing ? (
          <textarea
            value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
            rows={8}
            className="w-full rounded-md border border-surface-200 px-3 py-2 text-sm text-surface-800 focus:border-primary-300 focus:outline-none focus:ring-1 focus:ring-primary-300"
          />
        ) : (
          <div className="prose prose-sm max-w-none text-surface-700">
            {linkifyConcepts(feature.description, feature.concepts)}
          </div>
        )}
      </div>

      {/* Concepts */}
      {feature.concepts.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-surface-700">Related Concepts</h2>
          <div className="flex flex-wrap gap-2">
            {feature.concepts.map((c) => (
              <Link
                key={c.id}
                to={`/wiki/concepts/${c.slug}`}
                className="inline-flex items-center rounded-full border border-orange-200 bg-orange-50 px-2.5 py-1 text-xs font-medium text-orange-700 transition-colors hover:bg-orange-100"
              >
                {c.term}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* PRD References */}
      {feature.prd_references.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-surface-700">
            <FileText size={14} className="inline mr-1" />
            Source PRDs
          </h2>
          <div className="space-y-2">
            {feature.prd_references.map((ref, i) => (
              <div
                key={i}
                className="rounded-md border border-surface-200 bg-white p-3"
              >
                <div className="flex items-center justify-between">
                  <Link
                    to={`/prds/${ref.entity_id}`}
                    className="font-medium text-sm text-primary-600 hover:text-primary-700 hover:underline"
                  >
                    {ref.prd_title || "Untitled PRD"}
                    <ExternalLink size={12} className="inline ml-1" />
                  </Link>
                  <span
                    className={`text-[10px] rounded px-1.5 py-0.5 ${
                      ref.confidence === "extracted"
                        ? "bg-green-50 text-green-600"
                        : "bg-amber-50 text-amber-600"
                    }`}
                  >
                    {ref.confidence}
                  </span>
                </div>
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

      {/* Implementation */}
      {(hasPeople || hasTasks || hasPrs) && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-surface-700">Implementation</h2>
          <div className="grid gap-3 sm:grid-cols-3">
            {hasPeople && (
              <div className="rounded-md border border-surface-200 bg-white p-3">
                <div className="flex items-center gap-1.5 mb-2 text-xs font-medium text-surface-500">
                  <Users size={12} />
                  People
                </div>
                <div className="space-y-1">
                  {impl.people.map((p) => (
                    <div key={p.id} className="flex items-center justify-between text-sm">
                      <span className="text-surface-700">{p.name}</span>
                      <span className="text-[10px] text-surface-400">{p.role}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            {hasTasks && (
              <div className="rounded-md border border-surface-200 bg-white p-3">
                <div className="flex items-center gap-1.5 mb-2 text-xs font-medium text-surface-500">
                  <CheckSquare size={12} />
                  Tasks
                </div>
                <div className="space-y-1">
                  {impl.tasks.map((t, i) => (
                    <div key={i} className="text-sm text-surface-700">
                      {t.done}/{t.total} done
                      {t.in_progress > 0 && (
                        <span className="text-xs text-surface-400 ml-1">
                          ({t.in_progress} in progress)
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {hasPrs && (
              <div className="rounded-md border border-surface-200 bg-white p-3">
                <div className="flex items-center gap-1.5 mb-2 text-xs font-medium text-surface-500">
                  <GitPullRequest size={12} />
                  Pull Requests
                </div>
                <div className="space-y-1">
                  {impl.prs.map((pr, i) => (
                    <div key={i} className="text-sm text-surface-700">
                      {pr.count} PR{pr.count !== 1 ? "s" : ""} linked
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Related Features */}
      {feature.related_features.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-surface-700">Related Features</h2>
          <div className="flex flex-wrap gap-2">
            {feature.related_features.map((rf) => (
              <Link
                key={rf.id}
                to={`/wiki/features/${rf.slug}`}
                className="inline-flex items-center rounded-md border border-surface-200 bg-white px-3 py-1.5 text-sm text-surface-700 transition-colors hover:border-primary-200 hover:text-primary-700"
              >
                {rf.title}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
