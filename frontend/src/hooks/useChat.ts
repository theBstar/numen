import { useState, useCallback, useRef } from "react";
import {
  createConversation,
  getConversations,
  getChatMessages,
  deleteChatConversation,
  sendChatMessage,
  type Conversation,
  type ChatMessage,
  type EntityReference,
} from "@/services/api";
import { trackChatMessageSent } from "@/analytics/events";

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  streamingContent: string;
  streamingEntities: EntityReference[];
  activeTool: string | null;
  error: string | null;
}

export function useChat() {
  const [state, setState] = useState<ChatState>({
    conversations: [],
    activeConversationId: null,
    messages: [],
    isStreaming: false,
    streamingContent: "",
    streamingEntities: [],
    activeTool: null,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const loadConversations = useCallback(async () => {
    try {
      const convs = await getConversations();
      setState((s) => ({ ...s, conversations: convs }));
    } catch {
      // ignore
    }
  }, []);

  const selectConversation = useCallback(async (conversationId: string) => {
    try {
      const msgs = await getChatMessages(conversationId);
      setState((s) => ({
        ...s,
        activeConversationId: conversationId,
        messages: msgs,
        error: null,
      }));
    } catch {
      // ignore
    }
  }, []);

  const startNewConversation = useCallback(async () => {
    try {
      const conv = await createConversation();
      setState((s) => ({
        ...s,
        conversations: [conv, ...s.conversations],
        activeConversationId: conv.id,
        messages: [],
        error: null,
      }));
      return conv.id;
    } catch {
      return null;
    }
  }, []);

  const sendMessage = useCallback(
    async (content: string) => {
      trackChatMessageSent({ messageLength: content.length, hasAttachments: false });
      let conversationId = state.activeConversationId;
      if (!conversationId) {
        conversationId = await startNewConversation();
        if (!conversationId) return;
      }

      // Optimistic user message
      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };

      setState((s) => ({
        ...s,
        messages: [...s.messages, userMsg],
        isStreaming: true,
        streamingContent: "",
        streamingEntities: [],
        activeTool: null,
        error: null,
      }));

      const cid = conversationId;

      abortRef.current = sendChatMessage(
        cid,
        content,
        (token) => {
          setState((s) => ({
            ...s,
            streamingContent: s.streamingContent + token,
          }));
        },
        (tool) => {
          setState((s) => ({ ...s, activeTool: tool }));
        },
        () => {
          setState((s) => ({ ...s, activeTool: null }));
        },
        () => {
          setState((s) => {
            const assistantMsg: ChatMessage = {
              id: crypto.randomUUID(),
              role: "assistant",
              content: s.streamingContent,
              referenced_entities: s.streamingEntities.length > 0 ? s.streamingEntities : undefined,
              created_at: new Date().toISOString(),
            };
            return {
              ...s,
              messages: [...s.messages, assistantMsg],
              isStreaming: false,
              streamingContent: "",
              streamingEntities: [],
              activeTool: null,
            };
          });
          // Update conversation title in list
          loadConversations();
        },
        (error) => {
          setState((s) => ({
            ...s,
            isStreaming: false,
            streamingContent: "",
            error,
          }));
        },
        (entities) => {
          setState((s) => ({ ...s, streamingEntities: entities }));
        },
        (sanitizedContent) => {
          // Replace what was streamed: the raw text contained something
          // that had to be redacted.
          setState((s) => ({ ...s, streamingContent: sanitizedContent }));
        },
      );
    },
    [state.activeConversationId, startNewConversation, loadConversations],
  );

  const deleteConversation = useCallback(
    async (conversationId: string) => {
      try {
        await deleteChatConversation(conversationId);
        setState((s) => ({
          ...s,
          conversations: s.conversations.filter((c) => c.id !== conversationId),
          ...(s.activeConversationId === conversationId
            ? { activeConversationId: null, messages: [] }
            : {}),
        }));
      } catch {
        // ignore
      }
    },
    [],
  );

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
    setState((s) => ({
      ...s,
      isStreaming: false,
      streamingContent: "",
      activeTool: null,
    }));
  }, []);

  return {
    ...state,
    loadConversations,
    selectConversation,
    startNewConversation,
    sendMessage,
    deleteConversation,
    stopStreaming,
  };
}
