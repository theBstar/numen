import { type NodeViewProps, NodeViewWrapper } from "@tiptap/react";
import { FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";

/**
 * Inline chip rendered for prdMention nodes in the TipTap editor.
 * Displays as a styled pill with a document icon. Clicking navigates
 * to the referenced PRD (optionally scrolling to a section anchor).
 */
export function PrdMentionChip({ node }: NodeViewProps) {
  const navigate = useNavigate();
  const { prdId, prdTitle, sectionSlug } = node.attrs as {
    prdId: string;
    prdTitle: string;
    sectionSlug: string | null;
  };

  const label = sectionSlug ? `${prdTitle}#${sectionSlug}` : prdTitle;

  function handleClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    const path = sectionSlug
      ? `/prds/${prdId}#${sectionSlug}`
      : `/prds/${prdId}`;
    navigate(path);
  }

  return (
    <NodeViewWrapper as="span" className="inline">
      <span
        role="link"
        tabIndex={0}
        onClick={handleClick}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") handleClick(e as unknown as React.MouseEvent);
        }}
        className={cn(
          "inline-flex items-center gap-1 rounded-md px-1.5 py-0.5",
          "bg-blue-50 text-blue-700 text-sm font-medium",
          "cursor-pointer hover:bg-blue-100 transition-colors",
          "select-none",
        )}
      >
        <FileText className="h-3.5 w-3.5 shrink-0" />
        <span>{label}</span>
      </span>
    </NodeViewWrapper>
  );
}
