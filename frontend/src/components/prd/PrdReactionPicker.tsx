import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { PrdReactionResponse } from "@/types";

interface PrdReactionPickerProps {
  prdId: string;
  blockId: string;
  reactions: PrdReactionResponse[];
  onToggle: (emoji: string) => void;
  currentMemberId?: string;
}

const COMMON_EMOJIS = [
  { emoji: "\uD83D\uDC4D", label: "Thumbs up" },
  { emoji: "\uD83D\uDC4E", label: "Thumbs down" },
  { emoji: "\u2764\uFE0F", label: "Heart" },
  { emoji: "\uD83D\uDC40", label: "Eyes" },
  { emoji: "\uD83D\uDE80", label: "Rocket" },
  { emoji: "\uD83C\uDF89", label: "Party" },
  { emoji: "\uD83E\uDD14", label: "Thinking" },
  { emoji: "\uD83D\uDD25", label: "Fire" },
] as const;

export function PrdReactionPicker({
  reactions,
  onToggle,
  currentMemberId,
}: PrdReactionPickerProps) {
  // Build a lookup of existing reactions by emoji
  const reactionMap = new Map(reactions.map((r) => [r.emoji, r]));

  return (
    <TooltipProvider delayDuration={200}>
      <div className="flex flex-wrap items-center gap-1">
        {/* Existing reaction chips */}
        {reactions
          .filter((r) => r.count > 0)
          .map((reaction) => {
            const reactedByMe =
              currentMemberId !== undefined &&
              reaction.member_ids.includes(currentMemberId);

            return (
              <Tooltip key={reaction.emoji}>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors",
                      reactedByMe
                        ? "border-primary-300 bg-primary-50 text-primary-700 hover:bg-primary-100"
                        : "border-surface-200 bg-white text-surface-600 hover:bg-surface-50",
                    )}
                    onClick={() => onToggle(reaction.emoji)}
                  >
                    <span>{reaction.emoji}</span>
                    <span className="font-medium">{reaction.count}</span>
                  </button>
                </TooltipTrigger>
                <TooltipContent side="top" className="text-xs">
                  {reaction.count} reaction{reaction.count !== 1 ? "s" : ""}
                  {reactedByMe && " (including you)"}
                </TooltipContent>
              </Tooltip>
            );
          })}

        {/* Add reaction picker */}
        <div className="group relative">
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="inline-flex h-6 w-6 items-center justify-center rounded-full border border-dashed border-surface-200 text-surface-300 transition-colors hover:border-surface-400 hover:text-surface-500"
              >
                +
              </button>
            </TooltipTrigger>
            <TooltipContent side="top" className="text-xs">
              Add reaction
            </TooltipContent>
          </Tooltip>

          {/* Emoji picker dropdown */}
          <div className="invisible absolute bottom-full left-0 z-10 mb-1 flex gap-0.5 rounded-lg border border-surface-200 bg-white p-1 shadow-lg transition-all group-hover:visible">
            {COMMON_EMOJIS.map(({ emoji, label }) => {
              const existing = reactionMap.get(emoji);
              const isActive =
                existing !== undefined &&
                currentMemberId !== undefined &&
                existing.member_ids.includes(currentMemberId);

              return (
                <Tooltip key={emoji}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      className={cn(
                        "flex h-7 w-7 items-center justify-center rounded-md text-base transition-colors hover:bg-surface-100",
                        isActive && "bg-primary-50",
                      )}
                      onClick={() => onToggle(emoji)}
                    >
                      {emoji}
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="text-xs">
                    {label}
                  </TooltipContent>
                </Tooltip>
              );
            })}
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}
