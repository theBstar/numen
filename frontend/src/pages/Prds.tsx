import { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Plus,
  Upload,
  FileText,
  Pencil,
  Eye,
  Save,
  Download,
  Sparkles,
  History,
  SendHorizonal,
  MoreHorizontal,
  Trash2,
  ListPlus,
} from "lucide-react";
import { usePrd, usePrds, usePrdBlocks, usePrdCoverage } from "@/hooks/prdQueries";
import {
  useUpdatePrd,
  useDeletePrd,
  useCreatePrdVersion,
  useTransitionPrdStatus,
  useSavePrdBlocks,
} from "@/hooks/prdMutations";
import { ThreeColumnLayout } from "@/components/layouts/ThreeColumnLayout";
import { PrdSidebar } from "@/components/prd/PrdSidebar";
import { PrdReadView } from "@/components/prd/PrdReadView";
import { PrdEditView } from "@/components/prd/PrdEditView";
import { PrdLanding } from "@/components/prd/PrdLanding";
import { PrdRightPanel } from "@/components/prd/PrdRightPanel";
import { PrdStatusBadge } from "@/components/prd/PrdStatusBadge";
import { PrdExportDialog } from "@/components/prd/PrdExportDialog";
import { PrdAiCompleteDialog } from "@/components/prd/PrdAiCompleteDialog";
// PrdVersionHistory moved into edit toolbar actions
import { CreatePrdDialog } from "@/components/prd/CreatePrdDialog";
import { PrdImportDialog } from "@/components/prd/PrdImportDialog";
import { CreateTaskFromPrdDialog } from "@/components/prd/CreateTaskFromPrdDialog";
// EmptyState moved into PrdLanding
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

export function Prds() {
  const { id: routeId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [selectedId, setSelectedId] = useState<string | undefined>(routeId);
  const [editMode, setEditMode] = useState(false);

  // Dialogs
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [aiCompleteOpen, setAiCompleteOpen] = useState(false);
  const [createTaskOpen, setCreateTaskOpen] = useState(false);
  const [showVersionHistory, setShowVersionHistory] = useState(false);

  // Keep selectedId in sync with route param
  if (routeId && routeId !== selectedId) {
    setSelectedId(routeId);
  }

  // Queries
  const { data: prd } = usePrd(selectedId);
  const { data: coverage } = usePrdCoverage(selectedId);
  const { data: blocksData } = usePrdBlocks(selectedId);
  const { data: prdsData, isLoading: prdsLoading } = usePrds();
  const prdBlocks = blocksData?.items ?? [];

  // Mutations
  const updatePrd = useUpdatePrd();
  const deletePrd = useDeletePrd();
  const createVersion = useCreatePrdVersion();
  const transitionStatus = useTransitionPrdStatus();
  const savePrdBlocks = useSavePrdBlocks();

  const prds = prdsData?.items ?? [];

  const handleSelect = useCallback(
    (nodeId: string) => {
      setSelectedId(nodeId);
      setEditMode(false);
      navigate(`/prds/${nodeId}`, { replace: true });
    },
    [navigate],
  );

  const handleBack = useCallback(() => {
    setSelectedId(undefined);
    setEditMode(false);
    navigate("/prds", { replace: true });
  }, [navigate]);

  function handleDelete() {
    if (!selectedId) return;
    if (window.confirm("Are you sure you want to delete this PRD?")) {
      deletePrd.mutate(selectedId, {
        onSuccess: () => handleBack(),
      });
    }
  }

  function handleTransition(newStatus: string) {
    if (!selectedId) return;
    transitionStatus.mutate({ prdId: selectedId, status: newStatus });
  }

  function handleCreateVersion() {
    if (!selectedId) return;
    const message = window.prompt("Version message (optional):");
    createVersion.mutate({ prdId: selectedId, message: message ?? undefined });
  }

  function handleAiBlocksGenerated(
    aiBlocks: {
      block_type: string;
      content: Record<string, unknown>;
      position?: number;
      heading_level?: number | null;
    }[],
  ) {
    if (!selectedId) return;
    const ops = aiBlocks.map((b) => ({
      op: "create" as const,
      block_type: b.block_type,
      content: b.content,
      position: b.position ?? undefined,
      heading_level: b.heading_level ?? undefined,
    }));
    savePrdBlocks.mutate({ prdId: selectedId, operations: ops });
  }

  const nextStatuses = prd ? (STATUS_TRANSITIONS[prd.status] ?? []) : [];
  const canSendForReview =
    prd?.status === "draft" || prd?.status === "needs_revision";

  // Chat context
  const chatContextHint = prd?.title ?? undefined;

  // ── Toolbar ──
  const toolbar = (
    <>
      <div className="flex items-center gap-2">
        <FileText size={16} className="text-primary-600" />
        <h1 className="text-sm font-semibold text-surface-800">PRDs</h1>
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Edit/View toggle when PRD selected */}
      {selectedId && prd && (
        <>
          <PrdStatusBadge status={prd.status as PrdStatus} />

          {editMode ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setEditMode(false)}
            >
              <Eye size={14} className="mr-1.5" />
              View
            </Button>
          ) : (
            <Button size="sm" variant="outline" onClick={() => setEditMode(true)}>
              <Pencil size={14} className="mr-1.5" />
              Edit
            </Button>
          )}
        </>
      )}

      {/* Edit mode actions */}
      {selectedId && prd && editMode && (
        <>
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

          <Button
            size="sm"
            variant="outline"
            onClick={() => setAiCompleteOpen(true)}
          >
            <Sparkles size={14} className="mr-1.5" />
            AI Complete
          </Button>

          <Button
            size="sm"
            variant="outline"
            onClick={handleCreateVersion}
            disabled={createVersion.isPending}
          >
            <Save size={14} className="mr-1.5" />
            Save Version
          </Button>

          <Button
            size="sm"
            variant="outline"
            onClick={() => setExportOpen(true)}
          >
            <Download size={14} className="mr-1.5" />
            Export
          </Button>

          <Button
            size="sm"
            variant={showVersionHistory ? "default" : "outline"}
            onClick={() => setShowVersionHistory(!showVersionHistory)}
          >
            <History size={14} className="mr-1.5" />
            History
          </Button>

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
        </>
      )}

      {/* Import + New PRD (always visible) */}
      <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}>
        <Upload size={14} className="mr-1.5" />
        Import
      </Button>
      <Button size="sm" onClick={() => setCreateOpen(true)}>
        <Plus size={14} className="mr-1.5" />
        New PRD
      </Button>
    </>
  );

  // ── Sidebar ──
  const sidebar = (
    <PrdSidebar selectedId={selectedId} onSelect={handleSelect} />
  );

  // ── Right panel ──
  const rightPanel =
    selectedId && prd ? (
      <PrdRightPanel
        prd={prd}
        coverage={coverage ?? null}
        blocks={prdBlocks}
        onUpdate={(data) => updatePrd.mutate({ id: selectedId, data })}
      />
    ) : undefined;

  return (
    <>
      <ThreeColumnLayout
        sidebar={sidebar}
        sidebarHeader={
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-primary-600" />
            <span className="text-sm font-semibold text-surface-800">
              PRD Tree
            </span>
          </div>
        }
        toolbar={toolbar}
        rightPanel={rightPanel}
        rightPanelWidth={288}
        chatContextHint={chatContextHint}
      >
        {/* Main content */}
        {!selectedId ? (
          <PrdLanding
            prds={prds}
            isLoading={prdsLoading}
            onSelect={handleSelect}
            onCreateNew={() => setCreateOpen(true)}
          />
        ) : editMode ? (
          <PrdEditView prdId={selectedId} />
        ) : (
          <PrdReadView prdId={selectedId} />
        )}
      </ThreeColumnLayout>

      {/* Dialogs */}
      <CreatePrdDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        parentId={null}
        defaultNodeType="document"
      />
      <PrdImportDialog
        open={importOpen}
        onClose={() => setImportOpen(false)}
        parentFolderId={null}
      />
      {selectedId && (
        <>
          <PrdExportDialog
            open={exportOpen}
            onClose={() => setExportOpen(false)}
            prdId={selectedId}
            prdTitle={prd?.title ?? ""}
          />
          <PrdAiCompleteDialog
            open={aiCompleteOpen}
            onClose={() => setAiCompleteOpen(false)}
            prdId={selectedId}
            onComplete={handleAiBlocksGenerated}
          />
          <CreateTaskFromPrdDialog
            open={createTaskOpen}
            onClose={() => setCreateTaskOpen(false)}
            prdId={selectedId}
            prdTitle={prd?.title ?? ""}
          />
        </>
      )}
    </>
  );
}
