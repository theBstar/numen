import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { useLivingPrd, useResolveConflict } from "@/hooks/useLivingPrd";
import { LivingPrdSectionCard } from "@/components/living/LivingPrdSectionCard";
import { ProvenancePane } from "@/components/living/ProvenancePane";
import { formatRelativeTime } from "@/lib/utils";
import type { ConflictResolutionChoice } from "@/types/livingPrd";

/**
 * Living PRD view (`/prd/:id`). Reads a synthesized PRD and renders sections
 * with per-section provenance + live agent-fetch indicators. The right pane
 * exposes sources/agents/history tabs and a conflict resolution card when
 * the selected section has unresolved disagreement.
 */
export function LivingPrdView() {
  const { id } = useParams<{ id: string }>();
  const { data: prd, isLoading, isError, error } = useLivingPrd(id);
  const resolve = useResolveConflict();

  const [selectedId, setSelectedId] = useState<string | null>(null);

  const selectedSection = useMemo(() => {
    if (!prd) return null;
    const target = selectedId ?? prd.sections[0]?.id ?? null;
    return prd.sections.find((s) => s.id === target) ?? null;
  }, [prd, selectedId]);

  if (isLoading) {
    return (
      <div data-testid="living-prd-loading" className="p-8 text-sm text-muted-foreground">
        Loading PRD...
      </div>
    );
  }

  if (isError) {
    const status = (error as { status?: number } | undefined)?.status;
    return (
      <div data-testid="living-prd-error" className="p-8 text-sm text-rose-700" role="alert">
        {status === 404
          ? "PRD not found."
          : "Could not load this PRD. Try again in a moment."}
      </div>
    );
  }

  if (!prd) return null;

  const handleResolve = (conflictId: string) => (resolution: ConflictResolutionChoice) => {
    if (!id) return;
    resolve.mutate({ prdId: id, conflictId, resolution });
  };

  const conflictId = selectedSection?.conflict?.id;
  const resolveError = resolve.error
    ? (resolve.error as Error).message || "Resolution failed"
    : null;

  return (
    <div className="grid h-full grid-cols-[1fr_380px]" data-testid="living-prd-view">
      <main className="overflow-y-auto bg-white">
        <header
          className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3"
          data-testid="living-prd-topbar"
        >
          <nav className="flex items-center gap-2 text-xs text-muted-foreground" aria-label="Breadcrumb">
            <span>{prd.workspace}</span>
            <ChevronRight className="h-3 w-3" aria-hidden="true" />
            <span className="font-medium text-slate-900">{prd.title}</span>
          </nav>
          <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
            <span>
              <strong className="font-medium text-slate-900">{prd.readsToday}</strong> reads today
            </span>
            <span>last sync {formatRelativeTime(prd.lastSyncAt)}</span>
            <span
              data-testid="connection-status"
              data-status={prd.connectionStatus}
              className={
                prd.connectionStatus === "connected"
                  ? "text-emerald-600"
                  : prd.connectionStatus === "reconnecting"
                    ? "text-amber-600"
                    : "text-rose-600"
              }
            >
              ● {prd.connectionStatus}
            </span>
          </div>
        </header>

        <div className="mx-auto max-w-3xl px-6 py-8">
          <div className="mb-6 border-b border-slate-200 pb-4">
            <p className="mb-1 text-[11px] uppercase tracking-wide text-emerald-700">Living PRD</p>
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{prd.title}</h1>
          </div>

          {prd.sections.length === 0 ? (
            <div
              data-testid="living-prd-empty"
              className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-muted-foreground"
            >
              No indexed sources yet. Connect Notion, GDocs, Git, or Slack to start synthesizing this PRD.
            </div>
          ) : (
            <div className="space-y-2">
              {prd.sections.map((section) => (
                <LivingPrdSectionCard
                  key={section.id}
                  section={section}
                  selected={selectedSection?.id === section.id}
                  onSelect={() => setSelectedId(section.id)}
                  onOpenConflict={() => setSelectedId(section.id)}
                />
              ))}
            </div>
          )}
        </div>
      </main>

      <aside className="border-l border-slate-200 bg-slate-50" data-testid="living-prd-aside">
        <ProvenancePane
          section={selectedSection}
          onResolveConflict={
            conflictId ? handleResolve(conflictId) : () => {
              /* no-op when no conflict */
            }
          }
          isResolving={resolve.isPending}
          resolveError={resolveError}
        />
      </aside>
    </div>
  );
}
