import { useState } from "react";
import { ChevronDown, ChevronRight, List, Settings2 } from "lucide-react";
import { PrdMetadataPanel } from "./PrdMetadataPanel";
import type { PrdResponse, PrdCoverage, PrdBlockResponse, UpdatePrdPayload } from "@/types";

interface PrdRightPanelProps {
  prd: PrdResponse;
  coverage: PrdCoverage | null;
  blocks: PrdBlockResponse[];
  onUpdate: (data: UpdatePrdPayload) => void;
}

function extractTextFromContent(content: Record<string, unknown>): string {
  if (!content) return "";
  if (content.type === "text" && typeof content.text === "string") return content.text;
  const children = content.content as Record<string, unknown>[] | undefined;
  if (Array.isArray(children)) {
    return children.map((c) => extractTextFromContent(c)).join("").trim();
  }
  return "";
}

export function PrdRightPanel({ prd, coverage, blocks, onUpdate }: PrdRightPanelProps) {
  const [contentsOpen, setContentsOpen] = useState(true);

  // Extract heading sections from blocks
  const sections = blocks
    .filter((b) => b.block_type === "heading" && b.heading_level)
    .map((b) => ({
      slug: b.slug,
      title: extractTextFromContent(b.content) || "Untitled",
      level: b.heading_level ?? 1,
    }));

  const scrollToSection = (slug: string) => {
    const el = document.getElementById(slug);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Contents section (collapsible) */}
      {sections.length > 0 && (
        <div className="shrink-0 border-b border-surface-200">
          <button
            onClick={() => setContentsOpen(!contentsOpen)}
            className="flex w-full items-center gap-2 px-4 py-2.5 text-left hover:bg-surface-50 transition-colors"
          >
            {contentsOpen ? (
              <ChevronDown size={12} className="text-surface-400" />
            ) : (
              <ChevronRight size={12} className="text-surface-400" />
            )}
            <List size={12} className="text-surface-500" />
            <span className="text-xs font-semibold text-surface-600">Contents</span>
            <span className="ml-auto text-[10px] text-surface-400">{sections.length}</span>
          </button>
          {contentsOpen && (
            <div className="px-2 pb-2 space-y-0.5">
              {sections.map((section) => (
                <button
                  key={section.slug}
                  onClick={() => scrollToSection(section.slug)}
                  className="flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-left text-xs text-surface-600 hover:bg-surface-50 hover:text-primary-600 transition-colors"
                  style={{ paddingLeft: `${(section.level - 1) * 10 + 8}px` }}
                >
                  <span className="h-1 w-1 shrink-0 rounded-full bg-surface-300" />
                  <span className="truncate">{section.title}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Details section - scrollable */}
      <div className="flex-1 overflow-y-auto">
        <div className="flex items-center gap-2 px-4 py-2.5 border-b border-surface-100">
          <Settings2 size={12} className="text-surface-500" />
          <span className="text-xs font-semibold text-surface-600">Details</span>
        </div>
        <PrdMetadataPanel
          prd={prd}
          coverage={coverage}
          onUpdate={onUpdate}
        />
      </div>
    </div>
  );
}
