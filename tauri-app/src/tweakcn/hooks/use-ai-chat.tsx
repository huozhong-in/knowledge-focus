"use client";

import { useAIChatStore } from "@/tweakcn/store/ai-chat-store";

export function useAIChat() {
  const store = useAIChatStore();
  return store;
}
