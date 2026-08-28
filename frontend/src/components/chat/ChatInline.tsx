import { useState, useEffect, useRef } from "react";
import { MessageCircle, Send, Plus, Square, Loader2 } from "lucide-react";
import { useChat } from "@/hooks/useChat";
import { cn } from "@/lib/utils";
import { ChatMarkdown } from "@/components/chat/ChatMarkdown";

interface ChatInlineProps {
  contextHint?: string;
}

/**
 * Inline (non-floating) chat component for embedding in page layouts.
 * Uses the same useChat hook as the global ChatPanel but renders
 * within a flex container instead of a fixed-position overlay.
 */
export function ChatInline({ contextHint }: ChatInlineProps) {
  const [input, setInput] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const {
    messages,
    isStreaming,
    streamingContent,
    streamingEntities,
    activeTool,
    error,
    sendMessage,
    startNewConversation,
    stopStreaming,
  } = useChat();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    // If there is a context hint and no messages yet, prepend context
    let messageToSend = trimmed;
    if (contextHint && messages.length === 0) {
      messageToSend = `[Context: Currently viewing "${contextHint}"]\n\n${trimmed}`;
    }

    setInput("");
    sendMessage(messageToSend);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full flex-col bg-white">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-surface-200 px-3 py-2.5">
        <div className="flex items-center gap-2">
          <MessageCircle size={14} className="text-primary-600" />
          <span className="text-xs font-semibold text-surface-700">Ask AI</span>
        </div>
        <button
          onClick={() => startNewConversation()}
          className="rounded p-1 text-surface-400 hover:bg-surface-100 hover:text-surface-600"
          title="New conversation"
        >
          <Plus size={14} />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-3 py-3">
        {messages.length === 0 && !isStreaming && (
          <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center text-surface-400">
            <MessageCircle size={24} className="text-surface-300" />
            <p className="text-xs">
              Ask about PRDs, goals, tasks, or coverage...
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn("mb-2.5", msg.role === "user" ? "text-right" : "text-left")}
          >
            <div
              className={cn(
                "inline-block max-w-[90%] rounded-xl px-3 py-2 text-xs",
                msg.role === "user"
                  ? "rounded-br-sm bg-primary-600 text-white"
                  : "rounded-bl-sm bg-surface-100 text-surface-800",
              )}
            >
              {msg.role === "assistant" ? (
                <ChatMarkdown content={msg.content} entities={msg.referenced_entities} />
              ) : (
                <div className="whitespace-pre-wrap">{msg.content}</div>
              )}
            </div>
          </div>
        ))}

        {/* Streaming response */}
        {isStreaming && (
          <div className="mb-2.5 text-left">
            {activeTool && (
              <div className="mb-1 flex items-center gap-1 text-[10px] text-surface-400">
                <Loader2 size={10} className="animate-spin" />
                Querying {activeTool}...
              </div>
            )}
            {streamingContent && (
              <div className="inline-block max-w-[90%] rounded-xl rounded-bl-sm bg-surface-100 px-3 py-2 text-xs text-surface-800">
                <ChatMarkdown content={streamingContent} entities={streamingEntities} />
              </div>
            )}
            {!streamingContent && !activeTool && (
              <div className="flex items-center gap-1 text-[10px] text-surface-400">
                <Loader2 size={10} className="animate-spin" />
                Thinking...
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="mb-2.5 rounded-lg bg-red-50 px-3 py-1.5 text-[10px] text-red-600">
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-surface-200 p-2.5">
        <div className="flex items-end gap-1.5">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question..."
            rows={1}
            className="max-h-20 flex-1 resize-none rounded-lg border border-surface-200 bg-surface-50 px-2.5 py-2 text-xs outline-none transition-colors placeholder:text-surface-400 focus:border-primary-300 focus:ring-1 focus:ring-primary-300"
          />
          {isStreaming ? (
            <button
              onClick={stopStreaming}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-500 text-white hover:bg-red-600"
              title="Stop"
            >
              <Square size={12} />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary-600 text-white transition-colors hover:bg-primary-700 disabled:opacity-40"
              title="Send"
            >
              <Send size={12} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
