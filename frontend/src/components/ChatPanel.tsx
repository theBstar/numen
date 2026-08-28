import { useState, useEffect, useRef } from "react";
import { MessageCircle, X, Send, ArrowLeft, Trash2, Plus, Square, Loader2 } from "lucide-react";
import { useChat } from "@/hooks/useChat";
import { cn } from "@/lib/utils";
import { ChatMarkdown } from "@/components/chat/ChatMarkdown";

export function ChatPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [input, setInput] = useState("");
  const [showConversations, setShowConversations] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const {
    conversations,
    activeConversationId,
    messages,
    isStreaming,
    streamingContent,
    streamingEntities,
    activeTool,
    error,
    loadConversations,
    selectConversation,
    startNewConversation,
    sendMessage,
    deleteConversation,
    stopStreaming,
  } = useChat();

  useEffect(() => {
    if (isOpen) loadConversations();
  }, [isOpen, loadConversations]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingContent]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    setInput("");
    sendMessage(trimmed);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-primary-600 text-white shadow-lg transition-transform hover:scale-105 hover:bg-primary-700"
        title="Open AI Chat"
      >
        <MessageCircle size={24} />
      </button>
    );
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex h-[600px] w-[420px] flex-col overflow-hidden rounded-2xl border border-surface-200 bg-white shadow-2xl">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-surface-200 bg-primary-600 px-4 py-3 text-white">
        <div className="flex items-center gap-2">
          {showConversations && (
            <button onClick={() => setShowConversations(false)} className="hover:opacity-80">
              <ArrowLeft size={18} />
            </button>
          )}
          <MessageCircle size={18} />
          <span className="text-sm font-semibold">Numen AI</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowConversations(!showConversations)}
            className="rounded p-1 text-xs hover:bg-white/20"
            title="Conversations"
          >
            History
          </button>
          <button
            onClick={() => {
              startNewConversation();
              setShowConversations(false);
            }}
            className="rounded p-1 hover:bg-white/20"
            title="New conversation"
          >
            <Plus size={16} />
          </button>
          <button onClick={() => setIsOpen(false)} className="rounded p-1 hover:bg-white/20">
            <X size={16} />
          </button>
        </div>
      </div>

      {showConversations ? (
        /* Conversation list */
        <div className="flex-1 overflow-y-auto p-2">
          {conversations.length === 0 && (
            <p className="py-8 text-center text-sm text-surface-400">No conversations yet</p>
          )}
          {conversations.map((conv) => (
            <div
              key={conv.id}
              className={cn(
                "group flex cursor-pointer items-center justify-between rounded-lg px-3 py-2.5 text-sm transition-colors",
                conv.id === activeConversationId
                  ? "bg-primary-50 text-primary-700"
                  : "hover:bg-surface-100",
              )}
              onClick={() => {
                selectConversation(conv.id);
                setShowConversations(false);
              }}
            >
              <span className="truncate">{conv.title || "New conversation"}</span>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  deleteConversation(conv.id);
                }}
                className="hidden text-surface-400 hover:text-red-500 group-hover:block"
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      ) : (
        /* Chat view */
        <>
          <div className="flex-1 overflow-y-auto px-4 py-3">
            {messages.length === 0 && !isStreaming && (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-surface-400">
                <MessageCircle size={32} />
                <p className="text-sm">Ask me about your projects, team, goals...</p>
                <p className="text-xs text-surface-300">
                  e.g. "How many people do I need to hire to complete delayed projects on time?"
                </p>
              </div>
            )}

            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn("mb-3", msg.role === "user" ? "text-right" : "text-left")}
              >
                <div
                  className={cn(
                    "inline-block max-w-[85%] rounded-2xl px-4 py-2.5 text-sm",
                    msg.role === "user"
                      ? "rounded-br-md bg-primary-600 text-white"
                      : "rounded-bl-md bg-surface-100 text-surface-800",
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
              <div className="mb-3 text-left">
                {activeTool && (
                  <div className="mb-1 flex items-center gap-1.5 text-xs text-surface-400">
                    <Loader2 size={12} className="animate-spin" />
                    Querying {activeTool}...
                  </div>
                )}
                {streamingContent && (
                  <div className="inline-block max-w-[85%] rounded-2xl rounded-bl-md bg-surface-100 px-4 py-2.5 text-sm text-surface-800">
                    <ChatMarkdown content={streamingContent} entities={streamingEntities} />
                  </div>
                )}
                {!streamingContent && !activeTool && (
                  <div className="flex items-center gap-1.5 text-xs text-surface-400">
                    <Loader2 size={12} className="animate-spin" />
                    Thinking...
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600">
                {error}
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-surface-200 p-3">
            <div className="flex items-end gap-2">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about your projects, team, goals..."
                rows={1}
                className="max-h-24 flex-1 resize-none rounded-xl border border-surface-200 bg-surface-50 px-3 py-2.5 text-sm outline-none transition-colors focus:border-primary-300 focus:ring-1 focus:ring-primary-300"
              />
              {isStreaming ? (
                <button
                  onClick={stopStreaming}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-red-500 text-white hover:bg-red-600"
                  title="Stop"
                >
                  <Square size={16} />
                </button>
              ) : (
                <button
                  onClick={handleSend}
                  disabled={!input.trim()}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary-600 text-white transition-colors hover:bg-primary-700 disabled:opacity-40"
                  title="Send"
                >
                  <Send size={16} />
                </button>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
