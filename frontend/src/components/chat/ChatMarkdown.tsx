import { type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import type { EntityReference } from "@/services/api";
import type { EntityType } from "@/types";
import { EntityMention } from "./EntityMention";

/**
 * Replace entity name occurrences in React children with EntityMention chips.
 * Matches longest names first to avoid partial replacements.
 */
function renderWithEntities(
  children: ReactNode,
  entities: EntityReference[],
): ReactNode {
  if (!entities.length) return children;

  // Sort by name length descending so longer names match first
  const sorted = [...entities].sort((a, b) => b.name.length - a.name.length);

  function processNode(node: ReactNode): ReactNode {
    if (typeof node === "string") {
      return splitTextWithEntities(node, sorted);
    }
    if (Array.isArray(node)) {
      return node.map((child, i) => <span key={i}>{processNode(child)}</span>);
    }
    return node;
  }

  return processNode(children);
}

function splitTextWithEntities(
  text: string,
  entities: EntityReference[],
): ReactNode {
  const parts: ReactNode[] = [];
  let remaining = text;
  let keyIdx = 0;

  while (remaining.length > 0) {
    let earliestIdx = remaining.length;
    let matchedEntity: EntityReference | null = null;

    for (const ent of entities) {
      const idx = remaining.indexOf(ent.name);
      if (idx !== -1 && idx < earliestIdx) {
        earliestIdx = idx;
        matchedEntity = ent;
      }
    }

    if (!matchedEntity) {
      parts.push(remaining);
      break;
    }

    if (earliestIdx > 0) {
      parts.push(remaining.slice(0, earliestIdx));
    }

    parts.push(
      <EntityMention
        key={`em-${keyIdx++}`}
        type={matchedEntity.type as EntityType}
        name={matchedEntity.name}
        id={matchedEntity.id}
      />,
    );

    remaining = remaining.slice(earliestIdx + matchedEntity.name.length);
  }

  return parts.length === 1 ? parts[0] : <>{parts}</>;
}

function makeComponents(entities: EntityReference[]): Components {
  const withEntities = (children: ReactNode) =>
    entities.length > 0 ? renderWithEntities(children, entities) : children;

  return {
    h1: ({ children }) => (
      <h3 className="mb-1 mt-2 text-sm font-bold first:mt-0">{withEntities(children)}</h3>
    ),
    h2: ({ children }) => (
      <h3 className="mb-1 mt-2 text-sm font-bold first:mt-0">{withEntities(children)}</h3>
    ),
    h3: ({ children }) => (
      <h3 className="mb-1 mt-2 text-sm font-semibold first:mt-0">{withEntities(children)}</h3>
    ),
    p: ({ children }) => <p className="mb-1.5 last:mb-0">{withEntities(children)}</p>,
    ul: ({ children }) => <ul className="mb-1.5 ml-4 list-disc last:mb-0">{children}</ul>,
    ol: ({ children }) => <ol className="mb-1.5 ml-4 list-decimal last:mb-0">{children}</ol>,
    li: ({ children }) => <li className="mb-0.5">{withEntities(children)}</li>,
    strong: ({ children }) => <strong className="font-semibold">{withEntities(children)}</strong>,
    em: ({ children }) => <em className="italic">{children}</em>,
    code: ({ children, className }) => {
      const isBlock = className?.includes("language-");
      if (isBlock) {
        return (
          <code className="block overflow-x-auto rounded bg-surface-800 px-2 py-1.5 text-xs text-surface-100">
            {children}
          </code>
        );
      }
      return (
        <code className="rounded bg-surface-200 px-1 py-0.5 text-xs">{children}</code>
      );
    },
    pre: ({ children }) => <pre className="mb-1.5 last:mb-0">{children}</pre>,
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary-600 underline hover:text-primary-700"
      >
        {children}
      </a>
    ),
    hr: () => <hr className="my-2 border-surface-200" />,
  };
}

interface ChatMarkdownProps {
  content: string;
  entities?: EntityReference[] | null;
}

export function ChatMarkdown({ content, entities }: ChatMarkdownProps) {
  const components = makeComponents(entities ?? []);
  return (
    <ReactMarkdown components={components}>
      {content}
    </ReactMarkdown>
  );
}
