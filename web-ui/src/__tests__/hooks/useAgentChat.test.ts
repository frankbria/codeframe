'use client';

import { renderHook, act } from '@testing-library/react';
import { useAgentChat } from '@/hooks/useAgentChat';
import { fetchStreamTicket, verifyAuthAfterStreamFailure } from '@/lib/api';

// The session-chat WS fires the re-auth probe on a 1008 auth close (#651),
// and fetches a fresh single-use stream ticket per (re)connect attempt (#745).
jest.mock('@/lib/api', () => ({
  fetchStreamTicket: jest.fn(),
  verifyAuthAfterStreamFailure: jest.fn(),
}));
const mockVerify = verifyAuthAfterStreamFailure as jest.MockedFunction<
  typeof verifyAuthAfterStreamFailure
>;
const mockFetchTicket = fetchStreamTicket as jest.MockedFunction<
  typeof fetchStreamTicket
>;

// ── WebSocket mock ────────────────────────────────────────────────────

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  readyState: number = MockWebSocket.OPEN;
  sentMessages: string[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  // Real browsers always deliver a CloseEvent with a numeric `code`.
  onclose: ((event: { code: number }) => void) | null = null;
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
    this.onclose?.({ code: 1000 });
  }

  // Test helpers to simulate server events
  simulateOpen() {
    this.onopen?.();
  }

  simulateMessage(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  simulateClose(code = 1000) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code });
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

// `connectRef.current()` is async (it awaits `fetchStreamTicket()` before
// opening the WebSocket, issue #745) — flush the microtask queue so the
// pending connect finishes creating the WS instance before a test inspects
// `MockWebSocket.instances` or calls `getLatestWs()`. Unaffected by fake
// timers: only macrotasks (setTimeout/setInterval) are faked, not promises.
async function flushConnect() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

// ── Setup / teardown ──────────────────────────────────────────────────

let originalWebSocket: typeof WebSocket;

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
  mockVerify.mockClear();
  mockFetchTicket.mockReset();
  mockFetchTicket.mockResolvedValue('test-ticket');
  jest.useFakeTimers();

  // Set RAF mock AFTER useFakeTimers() — jest.useFakeTimers() replaces
  // requestAnimationFrame with its own implementation, so we must override it here.
  global.requestAnimationFrame = (cb: FrameRequestCallback) => {
    rafCallbacks.push(cb);
    return rafCallbacks.length;
  };
  global.cancelAnimationFrame = () => {};
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

/** Render the hook and flush the initial (async) connect attempt. */
async function renderConnected(sessionId: string | null) {
  const rendered = renderHook(
    ({ id }: { id: string | null }) => useAgentChat(id),
    { initialProps: { id: sessionId } }
  );
  await flushConnect();
  return rendered;
}

// ── Tests ─────────────────────────────────────────────────────────────

describe('useAgentChat', () => {
  describe('connection lifecycle', () => {
    it('does not connect when sessionId is null', async () => {
      renderHook(() => useAgentChat(null));
      await flushConnect();
      expect(MockWebSocket.instances).toHaveLength(0);
      expect(mockFetchTicket).not.toHaveBeenCalled();
    });

    it('connects to correct URL when sessionId is provided', async () => {
      await renderConnected('session-123');
      expect(MockWebSocket.instances).toHaveLength(1);
      expect(getLatestWs().url).toContain('/ws/sessions/session-123/chat');
      expect(getLatestWs().url).toContain('ticket=test-ticket');
      expect(getLatestWs().url).not.toContain('token=');
    });

    it('falls back to the bare URL (no ticket, no token) when the ticket fetch fails', async () => {
      mockFetchTicket.mockResolvedValue(null);
      await renderConnected('session-123');
      expect(getLatestWs().url).toContain('/ws/sessions/session-123/chat');
      expect(getLatestWs().url).not.toContain('ticket=');
      expect(getLatestWs().url).not.toContain('token=');
    });

    it('sets connected=true and status=idle on open', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });
      expect(result.current.state.connected).toBe(true);
      expect(result.current.state.status).toBe('idle');
    });

    it('disconnects on unmount', async () => {
      const { unmount } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });
      unmount();
      expect(getLatestWs().readyState).toBe(MockWebSocket.CLOSED);
    });

    it('sets connected=false and status=disconnected on close', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });
      act(() => { getLatestWs().simulateClose(); });
      expect(result.current.state.connected).toBe(false);
      expect(result.current.state.status).toBe('disconnected');
    });

    it('reconnects when sessionId changes', async () => {
      const { rerender } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      rerender({ id: 'session-2' });
      await flushConnect();

      expect(MockWebSocket.instances).toHaveLength(2);
      expect(getLatestWs().url).toContain('session-2');
    });
  });

  describe('auth-failure re-auth (#651)', () => {
    // The backend denies WS auth before accepting the handshake, so a real
    // browser reports an expired token as 1006 (abnormal), not 1008. The probe
    // must therefore fire on any non-normal close; it self-filters (only a
    // genuine 401 redirects), so transient closes still reconnect.
    it('fires the re-auth probe on an abnormal (1006) close', async () => {
      await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { getLatestWs().simulateClose(1006); });

      expect(mockVerify).toHaveBeenCalledTimes(1);
    });

    it('fires the re-auth probe on an explicit 1008 auth close', async () => {
      await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { getLatestWs().simulateClose(1008); });

      expect(mockVerify).toHaveBeenCalledTimes(1);
    });

    it('does not fire the probe on a clean (1000) close', async () => {
      await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { getLatestWs().simulateClose(1000); });

      expect(mockVerify).not.toHaveBeenCalled();
    });
  });

  describe('reconnect with exponential backoff', () => {
    it('auto-reconnects after disconnect (first attempt)', async () => {
      await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });
      act(() => { getLatestWs().simulateClose(); });
      act(() => { jest.advanceTimersByTime(1000); }); // BASE_RETRY_DELAY_MS * 2^0
      await flushConnect();
      expect(MockWebSocket.instances).toHaveLength(2);
    });

    it('mints a fresh ticket for each reconnect attempt (issue #745)', async () => {
      mockFetchTicket.mockResolvedValueOnce('tk-1').mockResolvedValueOnce('tk-2');
      await renderConnected('session-1');
      expect(getLatestWs().url).toContain('ticket=tk-1');

      act(() => { getLatestWs().simulateOpen(); });
      act(() => { getLatestWs().simulateClose(); });
      act(() => { jest.advanceTimersByTime(1000); });
      await flushConnect();

      expect(MockWebSocket.instances).toHaveLength(2);
      expect(getLatestWs().url).toContain('ticket=tk-2');
      expect(mockFetchTicket).toHaveBeenCalledTimes(2);
    });

    it('stops reconnecting after 5 attempts and sets error status', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      // Trigger 5 retries (closes 1-5 schedule retries, each advance fires the retry)
      for (let i = 0; i < 5; i++) {
        act(() => { getLatestWs().simulateClose(); });
        act(() => { jest.advanceTimersByTime(1000 * 2 ** i); });
        await flushConnect();
      }
      // retriesRef = 5; close the final retry connection to hit the error path
      act(() => { getLatestWs().simulateClose(); });

      expect(result.current.state.status).toBe('error');
      expect(result.current.state.error).toBe('Max reconnect attempts reached');
    });
  });

  describe('keepalive ping', () => {
    it('sends ping every 30 seconds after open', async () => {
      await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });
      const ws = getLatestWs();
      act(() => { jest.advanceTimersByTime(30000); });
      expect(ws.sentMessages.some((m) => m.includes('"type":"ping"'))).toBe(true);
    });
  });

  describe('message handling', () => {
    it('accumulates text_delta into streaming assistant message', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({ type: 'text_delta', content: 'Hello' });
        getLatestWs().simulateMessage({ type: 'text_delta', content: ' world' });
        flushRaf();
      });

      const msgs = result.current.state.messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].role).toBe('assistant');
      expect(msgs[0].content).toBe('Hello world');
      expect(result.current.state.status).toBe('streaming');
    });

    it('finalizes assistant message on done event', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({ type: 'text_delta', content: 'Done!' });
        flushRaf();
        getLatestWs().simulateMessage({ type: 'done' });
      });

      expect(result.current.state.status).toBe('idle');
    });

    it('pushes tool_use message with toolName and toolInput', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({
          type: 'tool_use_start',
          tool_name: 'read_file',
          tool_input: { path: '/foo.ts' },
        });
        flushRaf();
      });

      const msgs = result.current.state.messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].role).toBe('tool_use');
      expect(msgs[0].toolName).toBe('read_file');
      expect(msgs[0].toolInput).toEqual({ path: '/foo.ts' });
    });

    it('pushes tool_result message', async () => {
      const { result } = await renderConnected('session-1');
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

    it('pushes thinking message', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({ type: 'thinking', content: 'reasoning...' });
        flushRaf();
      });

      const msgs = result.current.state.messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].role).toBe('thinking');
    });

    it('updates cost on cost_update event', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({
          type: 'cost_update',
          cost_usd: 0.05,
          input_tokens: 1000,
          output_tokens: 500,
        });
      });

      expect(result.current.state.costUsd).toBe(0.05);
      expect(result.current.state.inputTokens).toBe(1000);
      expect(result.current.state.outputTokens).toBe(500);
    });

    it('sets error status on error event', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => {
        getLatestWs().simulateMessage({ type: 'error', message: 'something went wrong' });
      });

      expect(result.current.state.status).toBe('error');
      expect(result.current.state.error).toBe('something went wrong');
    });
  });

  describe('sendMessage', () => {
    it('pushes optimistic user message immediately', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { result.current.sendMessage('hello agent'); });

      const msgs = result.current.state.messages;
      expect(msgs).toHaveLength(1);
      expect(msgs[0].role).toBe('user');
      expect(msgs[0].content).toBe('hello agent');
    });

    it('sends message over WebSocket', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { result.current.sendMessage('hello agent'); });

      const ws = getLatestWs();
      const sent = ws.sentMessages.find((m) => m.includes('"type":"message"'));
      expect(sent).toBeDefined();
      expect(JSON.parse(sent!)).toEqual({ type: 'message', content: 'hello agent' });
    });

    it('sets status to thinking after sendMessage', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { result.current.sendMessage('hello'); });

      expect(result.current.state.status).toBe('thinking');
    });

    it('does not send when WS is not open', async () => {
      const { result } = await renderConnected('session-1');
      // Do not call simulateOpen — ws is in CONNECTING state by default
      getLatestWs().readyState = MockWebSocket.CLOSED;

      act(() => { result.current.sendMessage('hello'); });

      expect(result.current.state.messages).toHaveLength(0);
    });
  });

  describe('interrupt', () => {
    it('sends interrupt message over WebSocket', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { result.current.interrupt(); });

      const ws = getLatestWs();
      expect(ws.sentMessages.some((m) => m.includes('"type":"interrupt"'))).toBe(true);
    });
  });

  describe('clearMessages', () => {
    it('clears all messages and resets error', async () => {
      const { result } = await renderConnected('session-1');
      act(() => { getLatestWs().simulateOpen(); });

      act(() => { result.current.sendMessage('hello'); });
      act(() => { result.current.clearMessages(); });

      expect(result.current.state.messages).toHaveLength(0);
      expect(result.current.state.error).toBeNull();
    });
  });
});
