import { useState, useCallback, useRef, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Save,
  History,
  MoreHorizontal,
  Trash2,
  ChevronRight,
  Download,
  SendHorizonal,
  Sparkles,
  ListPlus,
} from "lucide-react";
import { usePrd, usePrdBlocks, usePrdCoverage } from "@/hooks/prdQueries";
import { useUpdatePrd, useDeletePrd, useCreatePrdVersion, useTransitionPrdStatus, useSavePrdBlocks } from "@/hooks/prdMutations";
import { PrdEditor } from "@/components/prd/PrdEditor";
import { PrdExportDialog } from "@/components/prd/PrdExportDialog";
import { PrdAiCompleteDialog } from "@/components/prd/PrdAiCompleteDialog";
import { CreateTaskFromPrdDialog } from "@/components/prd/CreateTaskFromPrdDialog";
import { PrdMetadataPanel } from "@/components/prd/PrdMetadataPanel";
import { PrdStatusBadge } from "@/components/prd/PrdStatusBadge";
import { PrdVersionHistory } from "@/components/prd/PrdVersionHistory";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import type { PrdStatus } from "@/types";

const STATUS_TRANSITIONS: Record<string, string[]> = {
  idea: ["draft"],
  draft: ["in_review"],
  in_review: ["needs_revision", "approved"],
  needs_revision: ["in_review"],
  approved: ["in_progress"],
  in_progress: ["shipped"],
  shipped: ["deprecated"],
  deprecated: ["archived"],
  archived: [],
};

export function PrdDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const { data: prd, isLoading: prdLoading } = usePrd(id);
  const { data: blocksData, isLoading: blocksLoading } = usePrdBlocks(id);
  const { data: coverage } = usePrdCoverage(id);

  const updatePrd = useUpdatePrd();
  const deletePrd = useDeletePrd();
  const createVersion = useCreatePrdVersion();
  const transitionStatus = useTransitionPrdStatus();
  const savePrdBlocks = useSavePrdBlocks();

  const [title, setTitle] = useState("");
  const [titleEditing, setTitleEditing] = useState(false);
  const [showVersionHistory, setShowVersionHistory] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [aiCompleteOpen, setAiCompleteOpen] = useState(false);
  const [createTaskOpen, setCreateTaskOpen] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);

  const blocks = blocksData?.items ?? [];

  // Sync title from server
  useEffect(() => {
    if (prd) {
      setTitle(prd.title);
    }
  }, [prd]);

  // Focus title input when editing
  useEffect(() => {
    if (titleEditing) {
      titleInputRef.current?.focus();
      titleInputRef.current?.select();
    }
  }, [titleEditing]);

  const handleTitleSave = useCallback(() => {
    if (!id || !title.trim() || title === prd?.title) {
      setTitle(prd?.title ?? "");
      setTitleEditing(false);
      return;
    }
    updatePrd.mutate({ id, data: { title: title.trim() } });
    setTitleEditing(false);
  }, [id, title, prd?.title, updatePrd]);

  function handleDelete() {
    if (!id) return;
    if (window.confirm("Are you sure you want to delete this PRD? This cannot be undone.")) {
      deletePrd.mutate(id, {
        onSuccess: () => navigate("/prds"),
      });
    }
  }

  function handleTransition(newStatus: string) {
    if (!id) return;
    transitionStatus.mutate({ prdId: id, status: newStatus });
  }

  function handleCreateVersion() {
    if (!id) return;
    const message = window.prompt("Version message (optional):");
    createVersion.mutate({ prdId: id, message: message ?? undefined });
  }

  function handleAiBlocksGenerated(aiBlocks: { block_type: string; content: Record<string, unknown>; position?: number; heading_level?: number | null }[]) {
    if (!id) return;
    const ops = aiBlocks.map((b) => ({
      op: "create" as const,
      block_type: b.block_type,
      content: b.content,
      position: b.position ?? undefined,
      heading_level: b.heading_level ?? undefined,
    }));
    savePrdBlocks.mutate({ prdId: id, operations: ops });
  }

  const nextStatuses = prd ? (STATUS_TRANSITIONS[prd.status] ?? []) : [];
  const canSendForReview = prd?.status === "draft" || prd?.status === "needs_revision";

  // Loading state
  if (prdLoading) {
    return (
      <div className="space-y-6">
        <div className="h-4 w-32 animate-pulse rounded bg-surface-200" />
        <div className="h-8 w-96 animate-pulse rounded bg-surface-200" />
        <div className="h-64 animate-pulse rounded-xl bg-surface-100" />
      </div>
    );
  }

  // Not found
  if (!prd) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate("/prds")}
          className="flex items-center gap-1 text-sm text-surface-500 hover:text-surface-700 transition-colors"
        >
          <ArrowLeft size={16} />
          Back to PRDs
        </button>
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          PRD not found.
        </div>
      </div>
    );
  }

  return (
    <div className="-mx-6 -my-8 flex h-[calc(100vh-0px)] overflow-hidden">
      {/* Main editor area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Sticky toolbar */}
        <div className="flex items-center justify-between border-b border-surface-200 bg-white px-6 py-2">
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate("/prds")}
              className="flex items-center gap-1 text-sm text-surface-500 hover:text-surface-700 transition-colors"
            >
              <ArrowLeft size={16} />
              PRDs
            </button>
            <ChevronRight size={14} className="text-surface-300" />
            <PrdStatusBadge status={prd.status} />
          </div>

          <div className="flex items-center gap-2">
            {/* Send for Review */}
            {canSendForReview && (
              <Button
                size="sm"
                onClick={() => handleTransition("in_review")}
                disabled={transitionStatus.isPending}
              >
                <SendHorizonal size={14} className="mr-1.5" />
                Send for Review
              </Button>
            )}

            {/* Status transition */}
            {nextStatuses.length > 0 && !canSendForReview && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="sm" variant="outline">
                    Move to...
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {nextStatuses.map((s) => (
                    <DropdownMenuItem
                      key={s}
                      onClick={() => handleTransition(s)}
                      disabled={transitionStatus.isPending}
                    >
                      <PrdStatusBadge status={s as PrdStatus} />
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            )}

            {/* AI Complete */}
            <Button
              size="sm"
              variant="outline"
              onClick={() => setAiCompleteOpen(true)}
            >
              <Sparkles size={14} className="mr-1.5" />
              AI Complete
            </Button>

            {/* Save version */}
            <Button
              size="sm"
              variant="outline"
              onClick={handleCreateVersion}
              disabled={createVersion.isPending}
            >
              <Save size={14} className="mr-1.5" />
              Save Version
            </Button>

            {/* Export */}
            <Button
              size="sm"
              variant="outline"
              onClick={() => setExportOpen(true)}
            >
              <Download size={14} className="mr-1.5" />
              Export
            </Button>

            {/* Version history toggle */}
            <Button
              size="sm"
              variant={showVersionHistory ? "default" : "outline"}
              onClick={() => setShowVersionHistory(!showVersionHistory)}
            >
              <History size={14} className="mr-1.5" />
              History
            </Button>

            {/* More actions */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="icon" variant="ghost">
                  <MoreHorizontal size={16} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => setCreateTaskOpen(true)}>
                  <ListPlus size={14} className="mr-2" />
                  Create Task
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={handleDelete}
                  className="text-red-600 focus:text-red-600"
                >
                  <Trash2 size={14} className="mr-2" />
                  Delete PRD
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Content + metadata panel */}
        <div className="flex flex-1 overflow-hidden">
          {/* Editor area */}
          <div className="flex-1 overflow-y-auto px-8 py-6">
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
                    setTitle(prd.title);
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
                {prd.title}
              </h1>
            )}

            {prd.description && (
              <p className="mt-2 text-sm text-surface-500">{prd.description}</p>
            )}

            {/* Block content area - TipTap editor */}
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
                    if (id) {
                      savePrdBlocks.mutate({ prdId: id, operations });
                    }
                  }}
                  readOnly={false}
                  entityId={id!}
                />
              )}
            </div>
          </div>

          {/* Right metadata panel */}
          <aside className="hidden w-72 shrink-0 border-l border-surface-200 bg-white overflow-hidden lg:block">
            <PrdMetadataPanel
              prd={prd}
              coverage={coverage ?? null}
              onUpdate={(data) => updatePrd.mutate({ id: id!, data })}
            />
          </aside>
        </div>
      </div>

      {/* Export dialog */}
      {id && <PrdExportDialog open={exportOpen} onClose={() => setExportOpen(false)} prdId={id} prdTitle={prd.title} />}

      {/* Create Task dialog */}
      <CreateTaskFromPrdDialog
        open={createTaskOpen}
        onClose={() => setCreateTaskOpen(false)}
        prdId={prd.id}
        prdTitle={prd.title}
      />

      {/* AI Complete dialog */}
      <PrdAiCompleteDialog
        open={aiCompleteOpen}
        onClose={() => setAiCompleteOpen(false)}
        prdId={prd.id}
        onComplete={handleAiBlocksGenerated}
      />

      {/* Version history panel */}
      {showVersionHistory && (
        <aside className="w-64 shrink-0 border-l border-surface-200 bg-white overflow-y-auto p-4">
          <PrdVersionHistory prdId={prd.id} />
        </aside>
      )}
    </div>
  );
}
