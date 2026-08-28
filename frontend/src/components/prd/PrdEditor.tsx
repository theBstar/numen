import { useCallback, useEffect, useRef, useState } from "react";
import { useEditor, EditorContent, type JSONContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { Extension } from "@tiptap/core";
import { Image } from "@tiptap/extension-image";
import { Table } from "@tiptap/extension-table";
import { TableRow } from "@tiptap/extension-table-row";
import { TableCell } from "@tiptap/extension-table-cell";
import { TableHeader } from "@tiptap/extension-table-header";
import { CodeBlockLowlight } from "@tiptap/extension-code-block-lowlight";
import { Link } from "@tiptap/extension-link";
import { Placeholder } from "@tiptap/extension-placeholder";
import { Underline } from "@tiptap/extension-underline";
import { TextAlign } from "@tiptap/extension-text-align";
import { Highlight } from "@tiptap/extension-highlight";
import { Typography } from "@tiptap/extension-typography";
import { Dropcursor } from "@tiptap/extension-dropcursor";
import { TaskList } from "@tiptap/extension-task-list";
import { TaskItem } from "@tiptap/extension-task-item";
import { common, createLowlight } from "lowlight";
import type { PrdBlockResponse, PrdBlockOperation } from "@/types";
import { cn } from "@/lib/utils";
import { PrdToolbar } from "./PrdToolbar";
import { SlashCommandExtension } from "./SlashCommand";
import { PrdMention } from "./extensions/PrdMention";
import { EntityMention } from "./extensions/EntityMention";

const lowlight = createLowlight(common);

/** Adds `id` attribute support to heading nodes for scroll-to anchors */
const HeadingId = Extension.create({
  name: "headingId",
  addGlobalAttributes() {
    return [
      {
        types: ["heading"],
        attributes: {
          id: {
            default: null,
            renderHTML: (attributes) => {
              if (!attributes.id) return {};
              return { id: attributes.id };
            },
            parseHTML: (element) => element.getAttribute("id"),
          },
        },
      },
    ];
  },
});

// ── Block <-> TipTap conversion utilities ──

/**
 * Map block_type strings to TipTap node types.
 */
function blockTypeToNodeType(blockType: string): string {
  switch (blockType) {
    case "heading":
      return "heading";
    case "paragraph":
      return "paragraph";
    case "bullet_list":
      return "bulletList";
    case "ordered_list":
      return "orderedList";
    case "task_list":
      return "taskList";
    case "code_block":
      return "codeBlock";
    case "blockquote":
      return "blockquote";
    case "image":
      return "image";
    case "table":
      return "table";
    case "horizontal_rule":
      return "horizontalRule";
    default:
      return "paragraph";
  }
}

function nodeTypeToBlockType(nodeType: string): string {
  switch (nodeType) {
    case "heading":
      return "heading";
    case "paragraph":
      return "paragraph";
    case "bulletList":
      return "bullet_list";
    case "orderedList":
      return "ordered_list";
    case "taskList":
      return "task_list";
    case "codeBlock":
      return "code_block";
    case "blockquote":
      return "blockquote";
    case "image":
      return "image";
    case "table":
      return "table";
    case "horizontalRule":
      return "horizontal_rule";
    default:
      return "paragraph";
  }
}

/**
 * Convert PrdBlockResponse[] into a TipTap JSON document.
 */
function blocksToDoc(blocks: PrdBlockResponse[]): JSONContent {
  const sorted = [...blocks].sort((a, b) => a.position - b.position);

  const content: JSONContent[] = sorted.map((block) => {
    // If the block content already has a valid TipTap JSON node, use it directly
    if (block.content && "type" in block.content) {
      const node = block.content as JSONContent;
      // Inject heading IDs for scroll-to support
      if (node.type === "heading" && block.slug) {
        node.attrs = { ...node.attrs, id: block.slug };
      }
      return node;
    }

    // Otherwise build a minimal TipTap node from block metadata
    const nodeType = blockTypeToNodeType(block.block_type);
    const node: JSONContent = { type: nodeType };

    if (block.block_type === "heading" && block.heading_level) {
      node.attrs = { level: block.heading_level, ...(block.slug ? { id: block.slug } : {}) };
    }

    // If block.content has a "text" field, wrap it as inline content
    const text = (block.content as Record<string, unknown>).text;
    if (typeof text === "string" && text.length > 0) {
      node.content = [{ type: "text", text }];
    }

    // If block.content has "src" for images
    const src = (block.content as Record<string, unknown>).src;
    if (nodeType === "image" && typeof src === "string") {
      node.attrs = {
        ...node.attrs,
        src,
        alt: ((block.content as Record<string, unknown>).alt as string) ?? "",
      };
    }

    return node;
  });

  // Ensure we always have at least one node
  if (content.length === 0) {
    content.push({ type: "paragraph" });
  }

  return { type: "doc", content };
}

/**
 * Extract top-level nodes from the current editor JSON and map back to block operations.
 */
function computeOperations(
  currentDoc: JSONContent,
  previousBlocks: PrdBlockResponse[],
): PrdBlockOperation[] {
  const ops: PrdBlockOperation[] = [];
  const currentNodes = currentDoc.content ?? [];
  const previousMap = new Map(previousBlocks.map((b) => [b.position, b]));
  const touchedPositions = new Set<number>();

  // Process current nodes
  currentNodes.forEach((node, index) => {
    const blockType = nodeTypeToBlockType(node.type ?? "paragraph");
    const headingLevel =
      node.type === "heading"
        ? ((node.attrs?.level as number | undefined) ?? null)
        : null;
    const content = node as Record<string, unknown>;

    const existingBlock = previousMap.get(index);
    touchedPositions.add(index);

    if (existingBlock) {
      // Check if content changed
      const changed =
        JSON.stringify(content) !== JSON.stringify(existingBlock.content) ||
        blockType !== existingBlock.block_type ||
        headingLevel !== existingBlock.heading_level;

      if (changed) {
        ops.push({
          op: "update",
          id: existingBlock.id,
          block_type: blockType,
          content,
          position: index,
          heading_level: headingLevel,
        });
      }
    } else {
      // New block
      ops.push({
        op: "create",
        block_type: blockType,
        content,
        position: index,
        heading_level: headingLevel,
      });
    }
  });

  // Detect deleted blocks
  for (const block of previousBlocks) {
    if (!touchedPositions.has(block.position)) {
      ops.push({
        op: "delete",
        id: block.id,
      });
    }
  }

  return ops;
}

// ── Props ──

interface PrdEditorProps {
  blocks: PrdBlockResponse[];
  onSave: (operations: PrdBlockOperation[]) => void;
  readOnly?: boolean;
  entityId: string;
}

export function PrdEditor({
  blocks,
  onSave,
  readOnly = false,
  entityId,
}: PrdEditorProps) {
  const [isSaving, setIsSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<string | null>(null);
  const previousBlocksRef = useRef<PrdBlockResponse[]>(blocks);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep previous blocks in sync when parent provides new blocks
  useEffect(() => {
    previousBlocksRef.current = blocks;
  }, [blocks]);

  const debouncedSave = useCallback(
    (doc: JSONContent) => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }

      saveTimerRef.current = setTimeout(() => {
        const ops = computeOperations(doc, previousBlocksRef.current);
        if (ops.length === 0) return;

        setIsSaving(true);
        try {
          onSave(ops);
          setLastSavedAt(new Date().toISOString());
        } finally {
          setIsSaving(false);
        }
      }, 2000);
    },
    [onSave],
  );

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => {
      if (saveTimerRef.current) {
        clearTimeout(saveTimerRef.current);
      }
    };
  }, []);

  const editor = useEditor(
    {
      extensions: [
        StarterKit.configure({
          codeBlock: false, // Replaced by CodeBlockLowlight
          dropcursor: false, // Using standalone Dropcursor
        }),
        Image.configure({
          HTMLAttributes: {
            class: "rounded-lg max-w-full mx-auto",
          },
        }),
        Table.configure({
          resizable: true,
          HTMLAttributes: {
            class: "border-collapse table-auto w-full",
          },
        }),
        TableRow,
        TableCell.configure({
          HTMLAttributes: {
            class: "border border-surface-200 px-3 py-2",
          },
        }),
        TableHeader.configure({
          HTMLAttributes: {
            class:
              "border border-surface-200 bg-surface-50 px-3 py-2 font-semibold text-left",
          },
        }),
        CodeBlockLowlight.configure({
          lowlight,
          HTMLAttributes: {
            class:
              "rounded-lg bg-surface-900 text-surface-100 p-4 text-sm font-mono",
          },
        }),
        Link.configure({
          openOnClick: false,
          HTMLAttributes: {
            class: "text-primary-600 underline underline-offset-2 cursor-pointer",
          },
        }),
        Placeholder.configure({
          placeholder: ({ node }) => {
            if (node.type.name === "heading") {
              return "Heading";
            }
            return 'Type "/" for commands...';
          },
        }),
        Underline,
        TextAlign.configure({
          types: ["heading", "paragraph"],
        }),
        Highlight.configure({
          HTMLAttributes: {
            class: "bg-yellow-200 rounded px-0.5",
          },
        }),
        Typography,
        Dropcursor.configure({
          color: "#6366f1",
          width: 2,
        }),
        TaskList.configure({
          HTMLAttributes: {
            class: "not-prose",
          },
        }),
        TaskItem.configure({
          nested: true,
          HTMLAttributes: {
            class: "flex items-start gap-2",
          },
        }),
        HeadingId,
        SlashCommandExtension,
        PrdMention,
        EntityMention,
      ],
      content: blocksToDoc(blocks),
      editable: !readOnly,
      editorProps: {
        attributes: {
          class:
            "prose prose-sm sm:prose-base max-w-none px-12 py-8 min-h-[60vh] focus:outline-none prose-pre:bg-transparent prose-pre:p-0",
        },
        handlePaste: (_view, event) => {
          // Handle pasted images
          const items = event.clipboardData?.items;
          if (!items) return false;

          for (const item of items) {
            if (item.type.startsWith("image/")) {
              event.preventDefault();
              const file = item.getAsFile();
              if (file) {
                // Create a temporary object URL for preview
                const url = URL.createObjectURL(file);
                editor?.chain().focus().setImage({ src: url }).run();
              }
              return true;
            }
          }
          return false;
        },
      },
      onUpdate: ({ editor: updatedEditor }) => {
        const doc = updatedEditor.getJSON();
        debouncedSave(doc);
      },
    },
    // Re-create editor when entityId changes (new document)
    [entityId, readOnly],
  );

  // Update content when blocks change externally (without re-creating editor)
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;

    const newDoc = blocksToDoc(blocks);
    const currentDoc = editor.getJSON();

    // Only update if content actually differs
    if (JSON.stringify(newDoc) !== JSON.stringify(currentDoc)) {
      editor.commands.setContent(newDoc);
    }
  }, [blocks, editor]);

  return (
    <div className={cn(
      "flex flex-1 flex-col overflow-hidden bg-white",
      !readOnly && "rounded-lg border border-surface-200",
    )}>
      {!readOnly && (
        <PrdToolbar
          editor={editor}
          isSaving={isSaving}
          lastSavedAt={lastSavedAt}
        />
      )}
      <div className="flex-1 overflow-y-auto">
        <EditorContent editor={editor} />
      </div>
    </div>
  );
}

// Re-export the editor hook for external use (e.g., PrdSectionNav needs the editor instance)
export { useEditor };
