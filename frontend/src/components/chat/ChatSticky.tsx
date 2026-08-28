import { useState, useEffect, useRef } from "react";
import {
  MessageCircle,
  Send,
  Square,
  ChevronUp,
  ChevronDown,
  Loader2,
  Plus,
} from "lucide-react";
import { useChat } from "@/hooks/useChat";
import { cn } from "@/lib/utils";
import { ChatMarkdown } from "@/components/chat/ChatMarkdown";

interface ChatStickyProps {
  contextHint?: string;
}

/**
 * Sticky bottom chat bar - always visible at the bottom of the content area.
 * Collapsed by default (just an input bar). Expands to show messages.
 */
export function ChatSticky({ contextHint }: ChatStickyProps) {
  const [expanded, setExpanded] = useState(false);
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
    if (expanded) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, streamingContent, expanded]);

  // Auto-expand when streaming starts
  useEffect(() => {
    if (isStreaming && !expanded) {
      setExpanded(true);
    }
  }, [isStreaming, expanded]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    let messageToSend = trimmed;
    if (contextHint && messages.length === 0) {
      messageToSend = `[Context: Currently viewing "${contextHint}"]\n\n${trimmed}`;
    }

    setInput("");
    setExpanded(true);
    sendMessage(messageToSend);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className={cn(
        "shrink-0 border-t border-surface-200 bg-white transition-all duration-200",
        expanded ? "max-h-[40vh]" : "max-h-[48px]",
      )}
    >
      {/* Expanded message area */}
      {expanded && (
        <div className="flex h-[calc(40vh-48px)] flex-col overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between border-b border-surface-100 px-3 py-1.5">
            <div className="flex items-center gap-2">
              <MessageCircle size={12} className="text-primary-600" />
              <span className="text-[11px] font-semibold text-surface-600">
                AI Chat
              </span>
              {contextHint && (
                <span className="text-[10px] text-surface-400 truncate max-w-[200px]">
                  - {contextHint}
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => startNewConversation()}
                className="rounded p-1 text-surface-400 hover:bg-surface-100 hover:text-surface-600"
                title="New conversation"
              >
                <Plus size={12} />
              </button>
              <button
                onClick={() => setExpanded(false)}
                className="rounded p-1 text-surface-400 hover:bg-surface-100 hover:text-surface-600"
                title="Collapse"
              >
                <ChevronDown size={12} />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-3 py-2">
            {messages.length === 0 && !isStreaming && (
              <div className="flex h-full items-center justify-center text-[11px] text-surface-400">
                Ask about PRDs, goals, tasks, or coverage...
              </div>
            )}

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "mb-2",
                  msg.role === "user" ? "text-right" : "text-left",
                )}
              >
                <div
                  className={cn(
                    "inline-block max-w-[85%] rounded-xl px-3 py-1.5 text-xs",
                    msg.role === "user"
                      ? "rounded-br-sm bg-primary-600 text-white"
                      : "rounded-bl-sm bg-surface-100 text-surface-800",
                  )}
                >
                  {msg.role === "assistant" ? (
                    <ChatMarkdown
                      content={msg.content}
                      entities={msg.referenced_entities}
                    />
                  ) : (
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  )}
                </div>
              </div>
            ))}

            {/* Streaming */}
            {isStreaming && (
              <div className="mb-2 text-left">
                {activeTool && (
                  <div className="mb-1 flex items-center gap-1 text-[10px] text-surface-400">
                    <Loader2 size={10} className="animate-spin" />
                    Querying {activeTool}...
                  </div>
                )}
                {streamingContent && (
                  <div className="inline-block max-w-[85%] rounded-xl rounded-bl-sm bg-surface-100 px-3 py-1.5 text-xs text-surface-800">
                    <ChatMarkdown
                      content={streamingContent}
                      entities={streamingEntities}
                    />
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
              <div className="mb-2 rounded-lg bg-red-50 px-3 py-1.5 text-[10px] text-red-600">
                {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        </div>
      )}

      {/* Input bar (always visible) */}
      <div className="flex h-[48px] items-center gap-2 px-3">
        {!expanded && (
          <button
            onClick={() => setExpanded(true)}
            className="flex items-center gap-1 rounded-md p-1.5 text-surface-400 hover:bg-surface-100 hover:text-surface-600"
            title="Expand chat"
          >
            <ChevronUp size={14} />
          </button>
        )}

        {!expanded && contextHint && (
          <span className="text-[10px] text-surface-400 truncate max-w-[150px]">
            {contextHint}
          </span>
        )}

        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => {
            if (messages.length > 0) setExpanded(true);
          }}
          placeholder="Ask AI a question..."
          rows={1}
          className="flex-1 resize-none rounded-lg border border-surface-200 bg-surface-50 px-2.5 py-1.5 text-xs outline-none transition-colors placeholder:text-surface-400 focus:border-primary-300 focus:ring-1 focus:ring-primary-300"
        />

        {isStreaming ? (
          <button
            onClick={stopStreaming}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-red-500 text-white hover:bg-red-600"
            title="Stop"
          >
            <Square size={11} />
          </button>
        ) : (
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-primary-600 text-white transition-colors hover:bg-primary-700 disabled:opacity-40"
            title="Send"
          >
            <Send size={11} />
          </button>
        )}
      </div>
    </div>
  );
}
