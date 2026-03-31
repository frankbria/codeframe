'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import type { AgentChatState, AgentChatStatus, ChatMessage, MessageRole } from '@/types';

export type { AgentChatState, ChatMessage, MessageRole };

// ── Constants ─────────────────────────────────────────────────────────

const WS_BASE_URL =
  (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_WS_URL) ||
  'ws://localhost:8000';

const MAX_RETRIES = 5;
const BASE_RETRY_DELAY_MS = 1000;
const PING_INTERVAL_MS = 30_000;

// ── Helpers ───────────────────────────────────────────────────────────

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('auth_token');
}

function generateId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID (e.g., jsdom in tests)
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function now(): string {
  return new Date().toISOString();
}

// ── Initial state ─────────────────────────────────────────────────────

const INITIAL_STATE: AgentChatState = {
  messages: [],
  status: 'idle',
  costUsd: 0,
  inputTokens: 0,
  outputTokens: 0,
  error: null,
  connected: false,
};

// ── Hook ──────────────────────────────────────────────────────────────

export interface UseAgentChat {
  state: AgentChatState;
  sendMessage: (content: string) => void;
  interrupt: () => void;
  clearMessages: () => void;
}

export function useAgentChat(sessionId: string | null): UseAgentChat {
  // ── Refs ──────────────────────────────────────────────────────────
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const rafRef = useRef<number | null>(null);
  const pendingDeltaRef = useRef('');
  const inProgressIdRef = useRef<string | null>(null);
  const stateRef = useRef<AgentChatState>({ ...INITIAL_STATE });

  // ── State ─────────────────────────────────────────────────────────
  const [state, setState] = useState<AgentChatState>({ ...INITIAL_STATE });

  const updateState = useCallback((patch: Partial<AgentChatState>) => {
    stateRef.current = { ...stateRef.current, ...patch };
    setState((prev) => ({ ...prev, ...patch }));
  }, []);

  // ── rAF flush for text_delta ──────────────────────────────────────
  const scheduleDeltaFlush = useCallback(() => {
    if (rafRef.current !== null) return;
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      const delta = pendingDeltaRef.current;
      if (!delta) return;
      pendingDeltaRef.current = '';

      const targetId = inProgressIdRef.current;
      stateRef.current = {
        ...stateRef.current,
        status: 'streaming',
        messages: stateRef.current.messages.map((m) =>
          m.id === targetId ? { ...m, content: m.content + delta } : m
        ),
      };
      setState({ ...stateRef.current });
    });
  }, []);

  // ── Disconnect cleanup ────────────────────────────────────────────
  const disconnect = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (pingTimerRef.current !== null) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
    if (retryTimerRef.current !== null) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      if (wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.close();
      }
      wsRef.current = null;
    }
  }, []);

  // ── connect (defined via ref to avoid stale closures) ────────────
  const connectRef = useRef<() => void>(() => {});

  connectRef.current = () => {
    if (!sessionId) return;

    updateState({ status: 'connecting' });

    const token = getToken() ?? '';
    const url = `${WS_BASE_URL}/ws/sessions/${sessionId}/chat?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      retriesRef.current = 0;
      updateState({ connected: true, status: 'idle' });
      pingTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, PING_INTERVAL_MS);
    };

    ws.onmessage = (event: MessageEvent) => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(event.data as string) as Record<string, unknown>;
      } catch {
        return;
      }

      const type = msg.type as string;

      if (type === 'text_delta') {
        const delta = (msg.content as string) ?? '';
        if (inProgressIdRef.current === null) {
          const newMsg: ChatMessage = {
            id: generateId(),
            role: 'assistant',
            content: '',
            createdAt: now(),
          };
          inProgressIdRef.current = newMsg.id;
          stateRef.current = {
            ...stateRef.current,
            messages: [...stateRef.current.messages, newMsg],
          };
          setState({ ...stateRef.current });
        }
        pendingDeltaRef.current += delta;
        scheduleDeltaFlush();
        return;
      }

      if (type === 'tool_use_start') {
        // Flush any pending delta before tool_use
        if (pendingDeltaRef.current && inProgressIdRef.current) {
          const delta = pendingDeltaRef.current;
          pendingDeltaRef.current = '';
          stateRef.current = {
            ...stateRef.current,
            messages: stateRef.current.messages.map((m) =>
              m.id === inProgressIdRef.current ? { ...m, content: m.content + delta } : m
            ),
          };
        }
        const newMsg: ChatMessage = {
          id: generateId(),
          role: 'tool_use',
          content: '',
          toolName: msg.tool_name as string | undefined,
          toolInput: msg.tool_input,
          createdAt: now(),
        };
        updateState({
          messages: [...stateRef.current.messages, newMsg],
          status: 'streaming',
        });
        return;
      }

      if (type === 'tool_result') {
        const newMsg: ChatMessage = {
          id: generateId(),
          role: 'tool_result',
          content: (msg.content as string) ?? '',
          createdAt: now(),
        };
        updateState({ messages: [...stateRef.current.messages, newMsg] });
        return;
      }

      if (type === 'thinking') {
        const newMsg: ChatMessage = {
          id: generateId(),
          role: 'thinking',
          content: (msg.content as string) ?? '',
          createdAt: now(),
        };
        updateState({ messages: [...stateRef.current.messages, newMsg] });
        return;
      }

      if (type === 'cost_update') {
        updateState({
          costUsd: (msg.cost_usd as number) ?? stateRef.current.costUsd,
          inputTokens: (msg.input_tokens as number) ?? stateRef.current.inputTokens,
          outputTokens: (msg.output_tokens as number) ?? stateRef.current.outputTokens,
        });
        return;
      }

      if (type === 'done') {
        // Flush any remaining delta
        if (pendingDeltaRef.current && inProgressIdRef.current) {
          const delta = pendingDeltaRef.current;
          pendingDeltaRef.current = '';
          stateRef.current = {
            ...stateRef.current,
            messages: stateRef.current.messages.map((m) =>
              m.id === inProgressIdRef.current ? { ...m, content: m.content + delta } : m
            ),
          };
        }
        inProgressIdRef.current = null;
        updateState({ status: 'idle' });
        return;
      }

      if (type === 'error') {
        updateState({
          status: 'error',
          error: (msg.message as string) ?? 'Unknown error',
        });
        return;
      }
    };

    ws.onclose = () => {
      if (pingTimerRef.current !== null) {
        clearInterval(pingTimerRef.current);
        pingTimerRef.current = null;
      }
      updateState({ connected: false, status: 'disconnected' });

      if (retriesRef.current < MAX_RETRIES) {
        const delay = BASE_RETRY_DELAY_MS * 2 ** retriesRef.current;
        retriesRef.current += 1;
        retryTimerRef.current = setTimeout(() => connectRef.current(), delay);
      } else {
        updateState({ status: 'error', error: 'Max reconnect attempts reached' });
      }
    };

    ws.onerror = () => {
      // onclose fires immediately after onerror — cleanup handled there
    };
  };

  // ── Effects ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!sessionId) return;
    connectRef.current();
    return () => disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // ── Public API ────────────────────────────────────────────────────
  const sendMessage = useCallback(
    (content: string) => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) return;

      const userMsg: ChatMessage = {
        id: generateId(),
        role: 'user',
        content,
        createdAt: now(),
      };
      updateState({
        messages: [...stateRef.current.messages, userMsg],
        status: 'thinking',
      });
      wsRef.current.send(JSON.stringify({ type: 'message', content }));
    },
    [updateState]
  );

  const interrupt = useCallback(() => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
  }, []);

  const clearMessages = useCallback(() => {
    updateState({ messages: [], error: null });
  }, [updateState]);

  return { state, sendMessage, interrupt, clearMessages };
}
