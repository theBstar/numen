import { useState } from "react";
import { Button } from "@/components/ui/button";
import { formatRelativeTime } from "@/lib/utils";
import type { Conflict, ConflictResolutionChoice } from "@/types/livingPrd";

export interface ConflictResolutionCardProps {
  conflict: Conflict;
  onResolve: (resolution: ConflictResolutionChoice) => void;
  isPending?: boolean;
  error?: string | null;
}

/**
 * Resolution card for a section conflict. Shows each source's claim and
 * lets the user either pick one source as canonical or type a manual
 * override.
 */
export function ConflictResolutionCard({
  conflict,
  onResolve,
  isPending,
  error,
}: ConflictResolutionCardProps) {
  const [manual, setManual] = useState("");

  return (
    <section
      data-testid="conflict-card"
      className="rounded-md border border-rose-200 bg-rose-50/50 p-3"
    >
      <header className="mb-2 text-xs font-semibold uppercase tracking-wide text-rose-700">
        Conflict between sources
      </header>
      <ul className="space-y-2">
        {conflict.sources.map((src) => (
          <li
            key={src.tag}
            data-testid={`conflict-source-${src.tag}`}
            className="rounded border border-rose-200 bg-white p-2"
          >
            <div className="mb-1 flex items-center justify-between">
              <span className="font-mono text-[11px] text-rose-700">{src.tag}</span>
              <span className="text-[11px] text-muted-foreground">
                {formatRelativeTime(src.queriedAt)}
              </span>
            </div>
            <p className="text-xs text-slate-700">{src.value}</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-2 h-7 text-[11px]"
              disabled={isPending}
              onClick={() =>
                onResolve({ kind: "pick_source", sourceTag: src.tag })
              }
            >
              Use this source
            </Button>
          </li>
        ))}
      </ul>
      <div className="mt-3 rounded border border-slate-200 bg-white p-2">
        <label
          htmlFor={`manual-resolution-${conflict.id}`}
          className="block text-[11px] font-medium text-slate-700"
        >
          Manual override
        </label>
        <textarea
          id={`manual-resolution-${conflict.id}`}
          value={manual}
          onChange={(e) => setManual(e.target.value)}
          rows={2}
          className="mt-1 w-full rounded border border-slate-200 px-2 py-1 text-xs"
          placeholder="Enter the canonical value..."
        />
        <Button
          variant="default"
          size="sm"
          className="mt-2 h-7 text-[11px]"
          disabled={isPending || manual.trim().length === 0}
          onClick={() => onResolve({ kind: "manual", value: manual.trim() })}
        >
          {isPending ? "Resolving..." : "Resolve with override"}
        </Button>
      </div>
      {error ? (
        <p className="mt-2 text-[11px] text-rose-700" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
