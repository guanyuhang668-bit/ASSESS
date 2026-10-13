/**
 * 轻量全局 store：追踪当前活跃的 ChatSession ID，
 * 供 Layout.tsx 心跳上报使用。
 */
import { create } from "zustand";

interface ActivityState {
  currentChatSessionId: number | null;
  setCurrentChatSessionId: (id: number | null) => void;
}

export const useActivityStore = create<ActivityState>((set) => ({
  currentChatSessionId: null,
  setCurrentChatSessionId: (id) => set({ currentChatSessionId: id }),
}));
