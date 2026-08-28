/**
 * EntityMention - TipTap Node extension for @person inline mentions.
 *
 * When the user types `@`, a suggestion popup shows org members.
 * Selecting one inserts an inline chip displaying @PersonName.
 *
 * Stored in TipTap JSON as:
 *   { type: "entityMention", attrs: { entityId, entityType, entityName } }
 */

import { Node, mergeAttributes, type Editor } from "@tiptap/core";
import { PluginKey } from "@tiptap/pm/state";
import { ReactNodeViewRenderer, ReactRenderer } from "@tiptap/react";
import Suggestion, {
  type SuggestionProps,
  type SuggestionKeyDownProps,
} from "@tiptap/suggestion";
import tippy, { type Instance as TippyInstance } from "tippy.js";

import { EntityMentionChip } from "./EntityMentionChip";
import {
  EntityMentionList,
  searchEntities,
  type EntityMentionItem,
  type EntityMentionListRef,
} from "./EntityMentionList";

// ── Node extension ──

export const EntityMention = Node.create({
  name: "entityMention",
  group: "inline",
  inline: true,
  atom: true,

  addAttributes() {
    return {
      entityId: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-entity-id"),
        renderHTML: (attributes) => ({
          "data-entity-id": attributes.entityId as string,
        }),
      },
      entityType: {
        default: "person",
        parseHTML: (element) => element.getAttribute("data-entity-type"),
        renderHTML: (attributes) => ({
          "data-entity-type": attributes.entityType as string,
        }),
      },
      entityName: {
        default: null,
        parseHTML: (element) => element.getAttribute("data-entity-name"),
        renderHTML: (attributes) => ({
          "data-entity-name": attributes.entityName as string,
        }),
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'span[data-type="entityMention"]',
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      "span",
      mergeAttributes({ "data-type": "entityMention" }, HTMLAttributes),
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(EntityMentionChip);
  },

  addProseMirrorPlugins() {
    return [
      Suggestion({
        pluginKey: new PluginKey("entityMention"),
        editor: this.editor,
        ...this.options.suggestion,
      }),
    ];
  },

  addOptions() {
    return {
      suggestion: entityMentionSuggestion,
    };
  },
});

// ── Suggestion configuration ──

export const entityMentionSuggestion = {
  char: "@",

  items: async ({ query }: { query: string }): Promise<EntityMentionItem[]> => {
    return searchEntities(query);
  },

  command: ({
    editor,
    range,
    props,
  }: {
    editor: Editor;
    range: { from: number; to: number };
    props: EntityMentionItem;
  }) => {
    // Insert the mention node followed by a space for continued typing
    editor
      .chain()
      .focus()
      .deleteRange(range)
      .insertContent([
        {
          type: "entityMention",
          attrs: {
            entityId: props.entityId,
            entityType: props.entityType,
            entityName: props.entityName,
          },
        },
        { type: "text", text: " " },
      ])
      .run();
  },

  render: () => {
    let component: ReactRenderer<EntityMentionListRef> | null = null;
    let popup: TippyInstance[] | null = null;

    return {
      onStart: (props: SuggestionProps<EntityMentionItem>) => {
        component = new ReactRenderer(EntityMentionList, {
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

      onUpdate(props: SuggestionProps<EntityMentionItem>) {
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
