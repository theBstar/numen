import { useState, useCallback, useRef, useEffect } from "react";
import { usePrd, usePrdBlocks } from "@/hooks/prdQueries";
import { useUpdatePrd, useSavePrdBlocks } from "@/hooks/prdMutations";
import { PrdEditor } from "./PrdEditor";

interface PrdEditViewProps {
  prdId: string;
}

export function PrdEditView({ prdId }: PrdEditViewProps) {
  const { data: prd } = usePrd(prdId);
  const { data: blocksData, isLoading: blocksLoading } = usePrdBlocks(prdId);
  const updatePrd = useUpdatePrd();
  const savePrdBlocks = useSavePrdBlocks();

  const [title, setTitle] = useState("");
  const [titleEditing, setTitleEditing] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);

  const blocks = blocksData?.items ?? [];

  // Sync title from server
  useEffect(() => {
    if (prd) setTitle(prd.title);
  }, [prd]);

  useEffect(() => {
    if (titleEditing) {
      titleInputRef.current?.focus();
      titleInputRef.current?.select();
    }
  }, [titleEditing]);

  const handleTitleSave = useCallback(() => {
    if (!title.trim() || title === prd?.title) {
      setTitle(prd?.title ?? "");
      setTitleEditing(false);
      return;
    }
    updatePrd.mutate({ id: prdId, data: { title: title.trim() } });
    setTitleEditing(false);
  }, [prdId, title, prd?.title, updatePrd]);

  return (
    <div className="px-8 py-6 max-w-4xl mx-auto">
      {/* Editable title */}
      {titleEditing ? (
        <input
          ref={titleInputRef}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={handleTitleSave}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleTitleSave();
            if (e.key === "Escape") {
              setTitle(prd?.title ?? "");
              setTitleEditing(false);
            }
          }}
          className="w-full border-none bg-transparent text-3xl font-bold text-surface-900 outline-none focus:ring-0"
        />
      ) : (
        <h1
          onClick={() => setTitleEditing(true)}
          className="cursor-text text-3xl font-bold text-surface-900 hover:text-surface-700"
        >
          {prd?.title ?? "Untitled"}
        </h1>
      )}

      {prd?.description && (
        <p className="mt-2 text-sm text-surface-500">{prd.description}</p>
      )}

      {/* Block content - TipTap editor */}
      <div className="mt-8">
        {blocksLoading ? (
          <div className="space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-6 animate-pulse rounded bg-surface-100"
                style={{ width: `${60 + Math.random() * 30}%` }}
              />
            ))}
          </div>
        ) : (
          <PrdEditor
            blocks={blocks}
            onSave={(operations) => {
              savePrdBlocks.mutate({ prdId, operations });
            }}
            readOnly={false}
            entityId={prdId}
          />
        )}
      </div>
    </div>
  );
}
