import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { useAiCompletePrd } from "@/hooks/prdMutations";
import type { AiCompletedBlock } from "@/types";
import {
  Sparkles,
  Loader2,
  Check,
  X,
  ChevronDown,
  ChevronUp,
  AlertCircle,
} from "lucide-react";

interface PrdAiCompleteDialogProps {
  open: boolean;
  onClose: () => void;
  prdId: string;
  onComplete: (blocks: AiCompletedBlock[]) => void;
}

const EXAMPLE_PROMPTS = [
  "A feature to allow users to export their data in CSV and PDF formats with custom filters",
  "Mobile push notification system for real-time alerts on task updates and mentions",
  "Integration with Figma to auto-sync design assets and link them to PRD sections",
  "Team dashboard showing sprint progress, blockers, and velocity trends",
];

interface SectionPreview {
  heading: string;
  blocks: AiCompletedBlock[];
  accepted: boolean;
  expanded: boolean;
}

function groupBlocksIntoSections(blocks: AiCompletedBlock[]): SectionPreview[] {
  const sections: SectionPreview[] = [];
  let currentSection: SectionPreview | null = null;

  for (const block of blocks) {
    if (block.block_type === "heading") {
      // Extract heading text from content
      const content = block.content as Record<string, unknown>;
      const headingContent = (content?.content as Array<Record<string, unknown>>) ?? [];
      const headingText =
        headingContent.length > 0 ? String(headingContent[0]?.text ?? "Untitled") : "Untitled";

      if (currentSection) {
        sections.push(currentSection);
      }
      currentSection = {
        heading: headingText,
        blocks: [block],
        accepted: true,
        expanded: false,
      };
    } else if (currentSection) {
      currentSection.blocks.push(block);
    } else {
      // Block before any heading - create a default section
      currentSection = {
        heading: "Introduction",
        blocks: [block],
        accepted: true,
        expanded: false,
      };
    }
  }

  if (currentSection) {
    sections.push(currentSection);
  }

  return sections;
}

function extractPlainText(content: Record<string, unknown>): string {
  const parts: string[] = [];

  if (typeof content.text === "string") {
    parts.push(content.text);
  }

  const children = content.content as Array<Record<string, unknown>> | undefined;
  if (Array.isArray(children)) {
    for (const child of children) {
      parts.push(extractPlainText(child));
    }
  }

  return parts.join(" ").trim();
}

export function PrdAiCompleteDialog({
  open,
  onClose,
  prdId,
  onComplete,
}: PrdAiCompleteDialogProps) {
  const [prompt, setPrompt] = useState("");
  const [sections, setSections] = useState<SectionPreview[]>([]);
  const [phase, setPhase] = useState<"input" | "preview">("input");

  const completeMutation = useAiCompletePrd(prdId);

  const handleGenerate = async () => {
    if (!prompt.trim()) return;

    try {
      const result = await completeMutation.mutateAsync(prompt.trim());
      const grouped = groupBlocksIntoSections(result.items);
      setSections(grouped);
      setPhase("preview");
    } catch {
      // Error handled by mutation state
    }
  };

  const handleAcceptAll = () => {
    const acceptedBlocks = sections
      .filter((s) => s.accepted)
      .flatMap((s) => s.blocks);
    onComplete(acceptedBlocks);
    handleClose();
  };

  const handleToggleSection = (index: number) => {
    setSections((prev) =>
      prev.map((s, i) => (i === index ? { ...s, accepted: !s.accepted } : s)),
    );
  };

  const handleToggleExpand = (index: number) => {
    setSections((prev) =>
      prev.map((s, i) => (i === index ? { ...s, expanded: !s.expanded } : s)),
    );
  };

  const handleClose = () => {
    setPrompt("");
    setSections([]);
    setPhase("input");
    completeMutation.reset();
    onClose();
  };

  const handleBack = () => {
    setPhase("input");
    setSections([]);
    completeMutation.reset();
  };

  const acceptedCount = sections.filter((s) => s.accepted).length;

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && handleClose()}>
      <DialogContent className="max-h-[85vh] overflow-hidden sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles className="h-5 w-5 text-violet-600" />
            {phase === "input" ? "AI Auto-Complete PRD" : "Preview Generated Content"}
          </DialogTitle>
          <DialogDescription>
            {phase === "input"
              ? "Describe the feature or product area, and AI will generate a complete PRD."
              : `Generated ${sections.length} sections. Toggle sections to include or exclude.`}
          </DialogDescription>
        </DialogHeader>

        {phase === "input" ? (
          <div className="space-y-4">
            <Textarea
              placeholder="Describe the feature, product area, or problem you want to write a PRD for..."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={6}
              className="resize-none text-sm"
              autoFocus
            />

            {/* Example prompts */}
            <div className="space-y-2">
              <p className="text-xs font-medium text-surface-500">Try an example:</p>
              <div className="flex flex-wrap gap-2">
                {EXAMPLE_PROMPTS.map((example, i) => (
                  <button
                    key={i}
                    type="button"
                    className="rounded-full border border-surface-200 bg-surface-50 px-3 py-1 text-xs text-surface-600 transition-colors hover:bg-surface-100 hover:text-surface-900"
                    onClick={() => setPrompt(example)}
                  >
                    {example.length > 60 ? `${example.slice(0, 60)}...` : example}
                  </button>
                ))}
              </div>
            </div>

            {completeMutation.isError && (
              <div className="flex items-center gap-2 rounded-md bg-red-50 p-3 text-sm text-red-700">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span>Failed to generate PRD content. Please try again.</span>
              </div>
            )}
          </div>
        ) : (
          <div className="max-h-[50vh] space-y-2 overflow-y-auto pr-1">
            {sections.map((section, index) => (
              <div
                key={index}
                className={cn(
                  "rounded-lg border transition-colors",
                  section.accepted
                    ? "border-surface-200 bg-white"
                    : "border-surface-100 bg-surface-50 opacity-60",
                )}
              >
                <div className="flex items-center gap-2 p-3">
                  <button
                    type="button"
                    className={cn(
                      "flex h-5 w-5 shrink-0 items-center justify-center rounded border transition-colors",
                      section.accepted
                        ? "border-violet-600 bg-violet-600 text-white"
                        : "border-surface-300 bg-white",
                    )}
                    onClick={() => handleToggleSection(index)}
                  >
                    {section.accepted && <Check className="h-3 w-3" />}
                  </button>
                  <button
                    type="button"
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    onClick={() => handleToggleExpand(index)}
                  >
                    <span className="truncate text-sm font-medium text-surface-900">
                      {section.heading}
                    </span>
                    <span className="shrink-0 text-xs text-surface-400">
                      {section.blocks.length - 1} block(s)
                    </span>
                    {section.expanded ? (
                      <ChevronUp className="ml-auto h-4 w-4 shrink-0 text-surface-400" />
                    ) : (
                      <ChevronDown className="ml-auto h-4 w-4 shrink-0 text-surface-400" />
                    )}
                  </button>
                </div>

                {section.expanded && (
                  <div className="border-t border-surface-100 px-3 py-2">
                    {section.blocks
                      .filter((b) => b.block_type !== "heading")
                      .map((block, bi) => {
                        const text = extractPlainText(
                          block.content as Record<string, unknown>,
                        );
                        return (
                          <p
                            key={bi}
                            className="mb-2 text-xs leading-relaxed text-surface-600 last:mb-0"
                          >
                            {text || "(empty block)"}
                          </p>
                        );
                      })}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          {phase === "input" ? (
            <>
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button
                onClick={handleGenerate}
                disabled={!prompt.trim() || completeMutation.isPending}
              >
                {completeMutation.isPending ? (
                  <>
                    <Loader2 className="mr-1.5 h-4 w-4 animate-spin" />
                    Generating...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-1.5 h-4 w-4" />
                    Generate PRD
                  </>
                )}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={handleBack}>
                Back
              </Button>
              <Button variant="ghost" onClick={handleClose}>
                <X className="mr-1.5 h-4 w-4" />
                Reject All
              </Button>
              <Button
                onClick={handleAcceptAll}
                disabled={acceptedCount === 0}
              >
                <Check className="mr-1.5 h-4 w-4" />
                Accept {acceptedCount === sections.length
                  ? "All"
                  : `${acceptedCount}/${sections.length}`}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
