import { useState } from "react";
import { Sparkles, Copy, Check, ExternalLink } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import { generateTaskPrompt } from "@/services/api";
import type { AiPromptResponse } from "@/types";

interface AiPromptModalProps {
  taskId: string;
}

export function AiPromptModal({ taskId }: AiPromptModalProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AiPromptResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [showRaw, setShowRaw] = useState(false);

  async function handleOpen(isOpen: boolean) {
    setOpen(isOpen);
    if (isOpen && !data) {
      setLoading(true);
      setError(null);
      try {
        const result = await generateTaskPrompt(taskId);
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to generate prompt");
      } finally {
        setLoading(false);
      }
    }
  }

  async function handleCopy() {
    if (!data) return;
    const text = showRaw ? data.raw_prompt : data.prompt;
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleRegenerate() {
    setData(null);
    setLoading(true);
    setError(null);
    generateTaskPrompt(taskId)
      .then(setData)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to generate prompt"))
      .finally(() => setLoading(false));
  }

  const promptText = data ? (showRaw ? data.raw_prompt : data.prompt) : "";

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogTrigger asChild>
        <button className="btn-secondary text-sm inline-flex items-center gap-1.5">
          <Sparkles size={14} className="text-amber-500" />
          AI Prompt
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Sparkles size={18} className="text-amber-500" />
            AI Coding Prompt
          </DialogTitle>
          <DialogDescription>
            {data ? (
              <span className="inline-flex items-center gap-3 text-xs">
                {data.goal_count > 0 && (
                  <span className="rounded-full bg-primary-100 px-2 py-0.5 text-primary-700">
                    {data.goal_count} goal{data.goal_count !== 1 ? "s" : ""}
                  </span>
                )}
                {data.has_blocking_chain && (
                  <span className="rounded-full bg-red-100 px-2 py-0.5 text-red-700">
                    Has blockers
                  </span>
                )}
                {data.repo_urls.length > 0 && (
                  <span className="rounded-full bg-surface-100 px-2 py-0.5 text-surface-600">
                    {data.repo_urls.length} repo{data.repo_urls.length !== 1 ? "s" : ""}
                  </span>
                )}
              </span>
            ) : (
              "Generating a rich prompt with task context, goals, and dependencies..."
            )}
          </DialogDescription>
        </DialogHeader>

        {/* Prompt content */}
        <div className="flex-1 overflow-hidden">
          {loading && (
            <div className="space-y-3 p-4">
              <div className="h-4 w-3/4 animate-pulse rounded bg-surface-200" />
              <div className="h-4 w-full animate-pulse rounded bg-surface-200" />
              <div className="h-4 w-5/6 animate-pulse rounded bg-surface-200" />
              <div className="h-4 w-2/3 animate-pulse rounded bg-surface-200" />
              <div className="h-4 w-full animate-pulse rounded bg-surface-200" />
              <div className="h-4 w-4/5 animate-pulse rounded bg-surface-200" />
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {error}
              <button onClick={handleRegenerate} className="ml-2 underline hover:no-underline">
                Retry
              </button>
            </div>
          )}

          {data && !loading && (
            <>
              {/* Toggle raw/refined */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setShowRaw(false)}
                    className={`text-xs px-2 py-1 rounded ${!showRaw ? "bg-primary-100 text-primary-700 font-medium" : "text-surface-500 hover:text-surface-700"}`}
                  >
                    Refined
                  </button>
                  <button
                    onClick={() => setShowRaw(true)}
                    className={`text-xs px-2 py-1 rounded ${showRaw ? "bg-primary-100 text-primary-700 font-medium" : "text-surface-500 hover:text-surface-700"}`}
                  >
                    Raw
                  </button>
                </div>
                {data.llm_trace && (
                  <span className="text-[10px] text-surface-400">
                    {(data.llm_trace as Record<string, unknown>).model as string}
                  </span>
                )}
              </div>
              <div className="overflow-y-auto max-h-[45vh] rounded-lg border border-surface-200 bg-surface-50 p-4">
                <pre className="whitespace-pre-wrap text-sm text-surface-800 font-mono leading-relaxed">
                  {promptText}
                </pre>
              </div>
            </>
          )}
        </div>

        {/* CTAs */}
        {data && !loading && (
          <DialogFooter className="flex-col gap-2 sm:flex-row">
            <div className="flex items-center gap-2 flex-1">
              <button
                onClick={handleCopy}
                className="btn-primary text-sm inline-flex items-center gap-1.5"
              >
                {copied ? <Check size={14} /> : <Copy size={14} />}
                {copied ? "Copied!" : "Copy to Clipboard"}
              </button>
              <a
                href="https://claude.ai/new"
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary text-sm inline-flex items-center gap-1.5"
              >
                <ExternalLink size={14} />
                Open Claude
              </a>
              <a
                href="https://cursor.com"
                target="_blank"
                rel="noopener noreferrer"
                className="btn-secondary text-sm inline-flex items-center gap-1.5"
              >
                <ExternalLink size={14} />
                Open Cursor
              </a>
            </div>
            <p className="text-[10px] text-surface-400 sm:self-center">
              For deeper integration, connect Numen via MCP in Settings
            </p>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
