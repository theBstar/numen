import { useCallback, useEffect, useState } from "react";
import { type Editor } from "@tiptap/react";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChevronRight, FileText } from "lucide-react";

interface PrdSectionNavProps {
  editor: Editor | null;
  activeSection?: string;
  onSectionClick: (slug: string) => void;
}

interface HeadingItem {
  level: number;
  text: string;
  slug: string;
  pos: number;
  children: HeadingItem[];
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
}

function extractHeadings(editor: Editor): HeadingItem[] {
  const headings: HeadingItem[] = [];
  const doc = editor.state.doc;

  doc.descendants((node, pos) => {
    if (node.type.name === "heading") {
      const level = node.attrs.level as number;
      const text = node.textContent;
      const slug = slugify(text);
      headings.push({ level, text, slug, pos, children: [] });
    }
  });

  return headings;
}

function buildTree(flatHeadings: HeadingItem[]): HeadingItem[] {
  const root: HeadingItem[] = [];
  const stack: HeadingItem[] = [];

  for (const heading of flatHeadings) {
    const item: HeadingItem = { ...heading, children: [] };

    while (stack.length > 0) {
      const parent = stack[stack.length - 1];
      if (parent && parent.level < item.level) {
        parent.children.push(item);
        stack.push(item);
        break;
      }
      stack.pop();
    }

    if (stack.length === 0) {
      root.push(item);
      stack.push(item);
    }
  }

  return root;
}

function HeadingNode({
  item,
  activeSection,
  onSectionClick,
  depth = 0,
}: {
  item: HeadingItem;
  activeSection?: string;
  onSectionClick: (slug: string) => void;
  depth?: number;
}) {
  const [isExpanded, setIsExpanded] = useState(true);
  const hasChildren = item.children.length > 0;
  const isActive = activeSection === item.slug;

  return (
    <div>
      <button
        type="button"
        onClick={() => onSectionClick(item.slug)}
        className={cn(
          "group flex w-full items-center gap-1 rounded-md px-2 py-1 text-left text-sm transition-colors",
          "hover:bg-surface-100",
          isActive
            ? "bg-primary-50 font-medium text-primary-700"
            : "text-surface-600",
        )}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
            className="flex h-4 w-4 shrink-0 items-center justify-center rounded hover:bg-surface-200"
          >
            <ChevronRight
              className={cn(
                "h-3 w-3 transition-transform",
                isExpanded && "rotate-90",
              )}
            />
          </button>
        ) : (
          <span className="h-4 w-4 shrink-0" />
        )}
        <span className="truncate">{item.text || "Untitled"}</span>
      </button>

      {hasChildren && isExpanded && (
        <div>
          {item.children.map((child) => (
            <HeadingNode
              key={`${child.slug}-${child.pos}`}
              item={child}
              activeSection={activeSection}
              onSectionClick={onSectionClick}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function PrdSectionNav({
  editor,
  activeSection,
  onSectionClick,
}: PrdSectionNavProps) {
  const [headings, setHeadings] = useState<HeadingItem[]>([]);

  const updateHeadings = useCallback(() => {
    if (!editor) return;
    const flat = extractHeadings(editor);
    const tree = buildTree(flat);
    setHeadings(tree);
  }, [editor]);

  useEffect(() => {
    if (!editor) return;

    // Initial extraction
    updateHeadings();

    // Re-extract on editor updates
    editor.on("update", updateHeadings);
    return () => {
      editor.off("update", updateHeadings);
    };
  }, [editor, updateHeadings]);

  if (headings.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-8 text-center">
        <FileText className="h-8 w-8 text-surface-300" />
        <p className="text-sm text-surface-400">
          Add headings to your document to see the table of contents.
        </p>
      </div>
    );
  }

  return (
    <ScrollArea className="h-full">
      <div className="px-2 py-3">
        <h3 className="mb-2 px-2 text-xs font-semibold uppercase tracking-wider text-surface-400">
          Contents
        </h3>
        <nav className="space-y-0.5">
          {headings.map((heading) => (
            <HeadingNode
              key={`${heading.slug}-${heading.pos}`}
              item={heading}
              activeSection={activeSection}
              onSectionClick={onSectionClick}
            />
          ))}
        </nav>
      </div>
    </ScrollArea>
  );
}
