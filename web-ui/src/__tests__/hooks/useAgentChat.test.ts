'use client';

import { renderHook, act } from '@testing-library/react';
import { useAgentChat } from '@/hooks/useAgentChat';

// ── WebSocket mock ────────────────────────────────────────────────────

type WsEventMap = {
  open?: () => void;
  message?: (event: { data: string }) => void;
  close?: () => void;
  error?: () => void;
};

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  readyState: number = MockWebSocket.OPEN;
  sentMessages: string[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  static instances: MockWebSocket[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sentMessages.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  // Test helpers to simulate server events
  simulateOpen() {
    this.onopen?.();
  }

  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  simulateClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  simulateError() {
    this.onerror?.();
  }
}

// ── RAF mock ──────────────────────────────────────────────────────────

let rafCallbacks: FrameRequestCallback[] = [];

function flushRaf() {
  const cbs = [...rafCallbacks];
  rafCallbacks = [];
  cbs.forEach((cb) => cb(performance.now()));
}

// ── Setup / teardown ──────────────────────────────────────────────────

let originalWebSocket: typeof WebSocket;
let originalLocalStorage: Storage;

beforeAll(() => {
  originalWebSocket = global.WebSocket;
  // @ts-expect-error mock
  global.WebSocket = MockWebSocket;
});

afterAll(() => {
  global.WebSocket = originalWebSocket;
});

beforeEach(() => {
  MockWebSocket.instances = [];
  rafCallbacks = [];
  jest.useFakeTimers();

  // Set RAF mock AFTER useFakeTimers() — jest.useFakeTimers() replaces
  // requestAnimationFrame with its own implementation, so we must override it here.
  global.requestAnimationFrame = (cb: FrameRequestCallback) => {
    rafCallbacks.push(cb);
    return rafCallbacks.length;
  };
  global.cancelAnimationFrame = () => {};

  // Set a fake auth token
  Object.defineProperty(window, 'localStorage', {
    value: {
      getItem: jest.fn().mockReturnValue('test-jwt-token'),
      setItem: jest.fn(),
      removeItem: jest.fn(),
    },
    writable: true,
  });
});

afterEach(() => {
  jest.useRealTimers();
  jest.clearAllMocks();
});

// ── Helper ────────────────────────────────────────────────────────────

function getLatestWs(): MockWebSocket {
  const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
  if (!ws) throw new Error('No WebSocket instance found');
  return ws;
}

// ── Tests ─────────────────────────────────────────────────────────────

describe('useAgentChat', () => {
  describe('connection lifecycle', () => {
    it('does not connect when sessionId is null', () => {
      renderHook(() => useAgentChat(null));
      expect(MockWebSocket.instances).toHaveLength(0);
    });

    it('connects to correct URL when sessionId is provided', () => {
      const { result } = renderHook(() => useAgentChat('session-123'));
      expect(MockWebSocket.instances).toHaveLength(1);
      expect(getLatestWs().url).toContain('/ws/sessions/session-123/chat');
      expect(getLatestWs().url).toContain('token=test-jwt-token');
      expect(result.current.state.status).toBe('connecting');
    });

    it('sets connected=true and status=idle on open', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });
      expect(result.current.state.connected).toBe(true);
      expect(result.current.state.status).toBe('idle');
    });

    it('disconnects on unmount', () => {
      const { unmount } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });
      unmount();
      expect(getLatestWs().readyState).toBe(MockWebSocket.CLOSED);
    });

    it('sets connected=false and status=disconnected on close', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });
      act(() => { getLatestWs().simulateClose(); });
      expect(result.current.state.connected).toBe(false);
      expect(result.current.state.status).toBe('disconnected');
    });

    it('reconnects when sessionId changes', () => {
      const { rerender } = renderHook(({ id }) => useAgentChat(id), {
        initialProps: { id: 'session-1' as string | null },
      });
      act(() => { getLatestWs().simulateOpen(); });
      rerender({ id: 'session-2' });
      expect(MockWebSocket.instances).toHaveLength(2);
      expect(getLatestWs().url).toContain('session-2');
    });
  });

  describe('reconnect with exponential backoff', () => {
    it('auto-reconnects after disconnect (first attempt)', () => {
      renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });
      act(() => { getLatestWs().simulateClose(); });
      act(() => { jest.advanceTimersByTime(1000); }); // BASE_RETRY_DELAY_MS * 2^0
      expect(MockWebSocket.instances).toHaveLength(2);
    });

    it('stops reconnecting after 5 attempts and sets error status', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      // Trigger 5 retries (closes 1-5 schedule retries, each advance fires the retry)
      for (let i = 0; i < 5; i++) {
        act(() => { getLatestWs().simulateClose(); });
        act(() => { jest.advanceTimersByTime(1000 * 2 ** i); });
      }
      // retriesRef = 5; close the final retry connection to hit the error path
      act(() => { getLatestWs().simulateClose(); });

      expect(result.current.state.status).toBe('error');
      expect(result.current.state.error).toBe('Max reconnect attempts reached');
    });
  });

  describe('keepalive ping', () => {
    it('sends ping every 30 seconds after open', () => {
      renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });
      const ws = getLatestWs();
      act(() => { jest.advanceTimersByTime(30000); });
      expect(ws.sentMessages.some((m) => m.includes('"type":"ping"'))).toBe(true);
    });
  });

  describe('message handling', () => {
    it('accumulates text_delta into streaming assistant message', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({ type: 'text_delta', delta: 'Hello' });
        getLatestWs().simulateMessage({ type: 'text_delta', delta: ' world' });
        flushRaf();
      });

      const msgs = result.current.state.messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].role).toBe('assistant');
      expect(msgs[0].content).toBe('Hello world');
      expect(result.current.state.status).toBe('streaming');
    });

    it('finalizes assistant message on done event', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({ type: 'text_delta', delta: 'Done!' });
        flushRaf();
        getLatestWs().simulateMessage({ type: 'done' });
      });

      expect(result.current.state.status).toBe('idle');
    });

    it('pushes tool_use message with toolName and toolInput', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({
          type: 'tool_use_start',
          toolName: 'read_file',
          toolInput: { path: '/foo.ts' },
        });
        flushRaf();
      });

      const msgs = result.current.state.messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].role).toBe('tool_use');
      expect(msgs[0].toolName).toBe('read_file');
      expect(msgs[0].toolInput).toEqual({ path: '/foo.ts' });
    });

    it('pushes tool_result message', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({ type: 'tool_result', content: 'file contents' });
        flushRaf();
      });

      const msgs = result.current.state.messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].role).toBe('tool_result');
      expect(msgs[0].content).toBe('file contents');
    });

    it('pushes thinking message', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({ type: 'thinking', content: 'reasoning...' });
        flushRaf();
      });

      const msgs = result.current.state.messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].role).toBe('thinking');
    });

    it('updates cost on cost_update event', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({
          type: 'cost_update',
          costUsd: 0.05,
          inputTokens: 1000,
          outputTokens: 500,
        });
      });

      expect(result.current.state.costUsd).toBe(0.05);
      expect(result.current.state.inputTokens).toBe(1000);
      expect(result.current.state.outputTokens).toBe(500);
    });

    it('sets error status on error event', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({ type: 'error', message: 'something went wrong' });
      });

      expect(result.current.state.status).toBe('error');
      expect(result.current.state.error).toBe('something went wrong');
    });
  });

  describe('sendMessage', () => {
    it('pushes optimistic user message immediately', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { result.current.sendMessage('hello agent'); });

      const msgs = result.current.state.messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].role).toBe('user');
      expect(msgs[0].content).toBe('hello agent');
    });

    it('sends message over WebSocket', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { result.current.sendMessage('hello agent'); });

      const ws = getLatestWs();
      const sent = ws.sentMessages.find((m) => m.includes('"type":"message"'));
      expect(sent).toBeDefined();
      expect(JSON.parse(sent!)).toEqual({ type: 'message', content: 'hello agent' });
    });

    it('sets status to thinking after sendMessage', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { result.current.sendMessage('hello'); });

      expect(result.current.state.status).toBe('thinking');
    });

    it('does not send when WS is not open', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      // Do not call simulateOpen — ws is in CONNECTING state by default
      getLatestWs().readyState = MockWebSocket.CLOSED;

      act(() => { result.current.sendMessage('hello'); });

      expect(result.current.state.messages).toHaveLength(0);
    });
  });

  describe('interrupt', () => {
    it('sends interrupt message over WebSocket', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { result.current.interrupt(); });

      const ws = getLatestWs();
      expect(ws.sentMessages.some((m) => m.includes('"type":"interrupt"'))).toBe(true);
    });
  });

  describe('clearMessages', () => {
    it('clears all messages and resets error', () => {
      const { result } = renderHook(() => useAgentChat('session-1'));
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { result.current.sendMessage('hello'); });
      act(() => { result.current.clearMessages(); });

      expect(result.current.state.messages).toHaveLength(0);
      expect(result.current.state.error).toBeNull();
    });
  });
});
