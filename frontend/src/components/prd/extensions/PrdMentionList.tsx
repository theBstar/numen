import {
  useState,
  useEffect,
  useCallback,
  useRef,
  forwardRef,
  useImperativeHandle,
} from "react";
import type { SuggestionKeyDownProps } from "@tiptap/suggestion";
import { FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { getPrds } from "@/services/api";
import type { PrdResponse, PrdStatus } from "@/types";
import { PrdStatusBadge } from "../PrdStatusBadge";

// ── Types ──

export interface PrdMentionItem {
  prdId: string;
  prdTitle: string;
  status: PrdStatus;
  sectionSlug: string | null;
}

export interface PrdMentionListRef {
  onKeyDown: (props: SuggestionKeyDownProps) => boolean;
}

interface PrdMentionListProps {
  items: PrdMentionItem[];
  command: (item: PrdMentionItem) => void;
}

// ── Component ──

export const PrdMentionList = forwardRef<PrdMentionListRef, PrdMentionListProps>(
  ({ items, command }, ref) => {
    const [selectedIndex, setSelectedIndex] = useState(0);
    const containerRef = useRef<HTMLDivElement>(null);

    const selectItem = useCallback(
      (index: number) => {
        const item = items[index];
        if (item) {
          command(item);
        }
      },
      [items, command],
    );

    useImperativeHandle(ref, () => ({
      onKeyDown: ({ event }: SuggestionKeyDownProps) => {
        if (event.key === "ArrowUp") {
          setSelectedIndex((prev) => (prev + items.length - 1) % items.length);
          return true;
        }
        if (event.key === "ArrowDown") {
          setSelectedIndex((prev) => (prev + 1) % items.length);
          return true;
        }
        if (event.key === "Enter") {
          selectItem(selectedIndex);
          return true;
        }
        return false;
      },
    }));

    useEffect(() => {
      setSelectedIndex(0);
    }, [items]);

    // Scroll selected item into view
    useEffect(() => {
      const container = containerRef.current;
      if (!container) return;
      const selected = container.querySelector(`[data-index="${selectedIndex}"]`);
      if (selected) {
        selected.scrollIntoView({ block: "nearest" });
      }
    }, [selectedIndex]);

    if (items.length === 0) {
      return (
        <div className="rounded-lg border border-surface-200 bg-white p-3 shadow-lg">
          <p className="text-sm text-surface-400">No PRDs found</p>
        </div>
      );
    }

    return (
      <div
        ref={containerRef}
        className="max-h-72 min-w-[280px] overflow-y-auto rounded-lg border border-surface-200 bg-white py-1 shadow-lg"
      >
        {items.map((item, index) => (
          <button
            key={item.prdId}
            type="button"
            data-index={index}
            onClick={() => selectItem(index)}
            className={cn(
              "flex w-full items-center gap-3 px-3 py-2 text-left transition-colors",
              index === selectedIndex
                ? "bg-primary-50 text-primary-700"
                : "text-surface-700 hover:bg-surface-50",
            )}
          >
            <div
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
                index === selectedIndex
                  ? "border-primary-200 bg-primary-100"
                  : "border-surface-200 bg-surface-50",
              )}
            >
              <FileText className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">{item.prdTitle}</p>
              <PrdStatusBadge status={item.status} className="mt-0.5" />
            </div>
          </button>
        ))}
      </div>
    );
  },
);
PrdMentionList.displayName = "PrdMentionList";

// ── Search helper ──

let searchTimer: ReturnType<typeof setTimeout> | null = null;

/**
 * Debounced search for PRDs. Returns PrdMentionItem[] suitable for
 * the suggestion plugin's items callback.
 */
export async function searchPrds(query: string): Promise<PrdMentionItem[]> {
  // Cancel any in-flight timer
  if (searchTimer) clearTimeout(searchTimer);

  try {
    const response = await getPrds({
      search: query,
      node_type: "document",
    });
    return response.items.map((prd: PrdResponse) => ({
      prdId: prd.id,
      prdTitle: prd.title,
      status: prd.status,
      sectionSlug: null,
    }));
  } catch {
    return [];
  }
}
