/**
 * PrdMention - TipTap Node extension for [[PRD Name]] cross-references.
 *
 * When the user types `[[`, a suggestion popup appears listing PRDs
 * from the org. Selecting one inserts an inline, non-editable chip
 * that links to the target PRD.
 *
 * The mention data is stored in TipTap JSON as node attributes:
 *   { type: "prdMention", attrs: { prdId, prdTitle, sectionSlug } }
 *
 * The backend event handler extracts these nodes to create REFERENCES
 * edges in FalkorDB.
 */

import { Node, mergeAttributes, type Editor } from "@tiptap/core";
import { PluginKey } from "@tiptap/pm/state";
import { ReactNodeViewRenderer, ReactRenderer } from "@tiptap/react";
import Suggestion, {
  type SuggestionProps,
  type SuggestionKeyDownProps,
} from "@tiptap/suggestion";
import tippy, { type Instance as TippyInstance } from "tippy.js";

import { PrdMentionChip } from "./PrdMentionChip";
import {
  PrdMentionList,
  searchPrds,
  type PrdMentionItem,
  type PrdMentionListRef,
} from "./PrdMentionList";

// ── Node extension ──

export const PrdMention = Node.create({
  name: "prdMention",
  group: "inline",
  inline: true,
  atom: true,

  addAttributes() {
    return {
      prdId: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-prd-id"),
        renderHTML: (attributes) => ({
          "data-prd-id": attributes.prdId as string,
        }),
      },
      prdTitle: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-prd-title"),
        renderHTML: (attributes) => ({
          "data-prd-title": attributes.prdTitle as string,
        }),
      },
      sectionSlug: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-section-slug"),
        renderHTML: (attributes) => {
          if (!attributes.sectionSlug) return {};
          return { "data-section-slug": attributes.sectionSlug as string };
        },
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-type="prdMention"]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes({ "data-type": "prdMention" }, HTMLAttributes),
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(PrdMentionChip);
  },

  addProseMirrorPlugins() {
    return [
      Suggestion({
        pluginKey: new PluginKey("prdMention"),
        editor: this.editor,
        ...this.options.suggestion,
      }),
    ];
  },

  addOptions() {
    return {
      suggestion: prdMentionSuggestion,
    };
  },
});

// ── Suggestion configuration ──

export const prdMentionSuggestion = {
  char: "[[",
  // Allow the suggestion to match after the trigger chars
  allowSpaces: true,

  items: async ({ query }: { query: string }): Promise<PrdMentionItem[]> => {
    return searchPrds(query);
  },

  command: ({
    editor,
    range,
    props,
  }: {
    editor: Editor;
    range: { from: number; to: number };
    props: PrdMentionItem;
  }) => {
    editor
      .chain()
      .focus()
      .deleteRange(range)
      .insertContent({
        type: "prdMention",
        attrs: {
          prdId: props.prdId,
          prdTitle: props.prdTitle,
          sectionSlug: props.sectionSlug,
        },
      })
      .run();
  },

  render: () => {
    let component: ReactRenderer<PrdMentionListRef> | null = null;
    let popup: TippyInstance[] | null = null;

    return {
      onStart: (props: SuggestionProps<PrdMentionItem>) => {
        component = new ReactRenderer(PrdMentionList, {
          props: {
            items: props.items,
            command: props.command,
          },
          editor: props.editor,
        });

        if (!props.clientRect) return;

        popup = tippy("body", {
          getReferenceClientRect: props.clientRect as () => DOMRect,
          appendTo: () => document.body,
          content: component.element,
          showOnCreate: true,
          interactive: true,
          trigger: "manual",
          placement: "bottom-start",
        });
      },

      onUpdate(props: SuggestionProps<PrdMentionItem>) {
        component?.updateProps({
          items: props.items,
          command: props.command,
        });

        if (!props.clientRect || !popup?.[0]) return;

        popup[0].setProps({
          getReferenceClientRect: props.clientRect as () => DOMRect,
        });
      },

      onKeyDown(props: SuggestionKeyDownProps) {
        if (props.event.key === "Escape") {
          popup?.[0]?.hide();
          return true;
        }
        return component?.ref?.onKeyDown(props) ?? false;
      },

      onExit() {
        popup?.[0]?.destroy();
        component?.destroy();
      },
    };
  },
};
