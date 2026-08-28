import { Link } from "react-router-dom";
import type { WikiConceptBrief } from "@/types";
import type { ReactNode } from "react";

/**
 * Scans description text for concept terms and wraps matches with
 * clickable Link elements to /wiki/concepts/{slug}.
 *
 * Uses word-boundary matching, case-insensitive, longest-match-first
 * to avoid partial matches (e.g., "administrator" won't match "admin").
 */
export function linkifyConcepts(
  text: string,
  concepts: WikiConceptBrief[],
): ReactNode {
  if (!text || concepts.length === 0) {
    return <>{text}</>;
  }

  // Sort concepts by term length (longest first) to avoid partial matches
  const sorted = [...concepts].sort((a, b) => b.term.length - a.term.length);

  // Build a single regex pattern with word boundaries
  const escaped = sorted.map((c) =>
    c.term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
  );
  const pattern = new RegExp(`\\b(${escaped.join("|")})\\b`, "gi");

  // Build a slug lookup map (case-insensitive)
  const slugMap = new Map<string, WikiConceptBrief>();
  for (const c of sorted) {
    slugMap.set(c.term.toLowerCase(), c);
  }

  // Split text into segments: plain text and matched terms
  const parts: ReactNode[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    const matchedTerm = match[1] ?? match[0];

    // Add plain text before this match
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const concept = slugMap.get(matchedTerm.toLowerCase());

    if (concept) {
      parts.push(
        <Link
          key={`${concept.slug}-${match.index}`}
          to={`/wiki/concepts/${concept.slug}`}
          className="text-orange-600 underline decoration-orange-200 underline-offset-2 hover:text-orange-700 hover:decoration-orange-400"
        >
          {matchedTerm}
        </Link>,
      );
    } else {
      parts.push(matchedTerm);
    }

    lastIndex = match.index + matchedTerm.length;
  }

  // Add remaining text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return <>{parts}</>;
}
