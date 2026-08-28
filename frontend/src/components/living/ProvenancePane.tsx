import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatRelativeTime } from "@/lib/utils";
import { ConflictResolutionCard } from "./ConflictResolutionCard";
import { SourceDotStack } from "./SourceDotStack";
import type {
  ConflictResolutionChoice,
  LivingPrdSection,
} from "@/types/livingPrd";

export interface ProvenancePaneProps {
  section: LivingPrdSection | null;
  onResolveConflict: (resolution: ConflictResolutionChoice) => void;
  isResolving?: boolean;
  resolveError?: string | null;
}

/**
 * Right pane: tabs for sources, agents, and history. The selected section
 * drives the content - if no section is selected we show a hint instead.
 */
export function ProvenancePane({
  section,
  onResolveConflict,
  isResolving,
  resolveError,
}: ProvenancePaneProps) {
  if (!section) {
    return (
      <div
        data-testid="provenance-empty"
        className="flex h-full items-center justify-center p-6 text-center text-xs text-muted-foreground"
      >
        Select a section to see its provenance.
      </div>
    );
  }

  return (
    <div data-testid="provenance-pane" className="flex h-full flex-col p-3">
      <header className="mb-3">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
          Selected section
        </p>
        <h2 className="text-sm font-semibold text-foreground">{section.title}</h2>
      </header>

      <Tabs defaultValue="sources" className="flex flex-1 flex-col">
        <TabsList className="self-start">
          <TabsTrigger value="sources">Sources</TabsTrigger>
          <TabsTrigger value="agents">Agents</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="sources" className="flex-1 space-y-3">
          {section.conflict ? (
            <ConflictResolutionCard
              conflict={section.conflict}
              onResolve={onResolveConflict}
              isPending={isResolving}
              error={resolveError}
            />
          ) : null}
          <ul className="space-y-2" data-testid="sources-list">
            {section.sources.map((src, idx) => (
              <li
                key={`${src.type}-${idx}`}
                className="flex items-center justify-between rounded border border-slate-200 bg-white px-2 py-1.5"
              >
                <span className="flex items-center gap-2 text-xs">
                  <SourceDotStack sources={[src]} />
                  <span className="capitalize text-slate-700">{src.type}</span>
                </span>
                <span className="font-mono text-[11px] tabular-nums text-muted-foreground">
                  {(src.weight * 100).toFixed(0)}%
                </span>
              </li>
            ))}
            {section.sources.length === 0 ? (
              <li className="text-xs text-muted-foreground">No sources indexed yet.</li>
            ) : null}
          </ul>
        </TabsContent>

        <TabsContent value="agents" className="flex-1">
          {section.recentAgentReads.length === 0 ? (
            <p className="text-xs text-muted-foreground">No agent reads yet.</p>
          ) : (
            <ul className="space-y-1" data-testid="agents-list">
              {section.recentAgentReads.map((read) => (
                <li
                  key={`${read.agentId}-${read.when}`}
                  className="flex items-center justify-between rounded border border-slate-200 bg-white px-2 py-1.5 text-xs"
                >
                  <span className="font-mono">#{read.taskId}</span>
                  <span className="text-muted-foreground">
                    {read.agentId} · {formatRelativeTime(read.when)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </TabsContent>

        <TabsContent value="history" className="flex-1">
          <p className="text-xs text-muted-foreground">
            History stream will populate once Lane B emits section-level events.
          </p>
        </TabsContent>
      </Tabs>
    </div>
  );
}
