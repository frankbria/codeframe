import { TextEncoder as NodeTextEncoder } from 'util';
import { renderHook, act } from '@testing-library/react';
import { useTerminalSocket } from '@/hooks/useTerminalSocket';
import { verifyAuthAfterStreamFailure } from '@/lib/api';

// The terminal WS fires the re-auth probe on a 4001 auth close (#651), and
// buildUrl mints a fresh single-use stream ticket per (re)connect (#745).
jest.mock('@/lib/api', () => ({ verifyAuthAfterStreamFailure: jest.fn() }));
const mockVerify = verifyAuthAfterStreamFailure as jest.MockedFunction<
  typeof verifyAuthAfterStreamFailure
>;

// ── WebSocket mock ────────────────────────────────────────────────────────

class MockWebSocket {
  static OPEN = 1;
  static CLOSED = 3;
  static CONNECTING = 0;

  url: string;
  binaryType: string = 'blob';
  readyState: number = MockWebSocket.CONNECTING;
  sent: (string | ArrayBuffer)[] = [];

  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string | ArrayBuffer }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;

  static instances: MockWebSocket[] = [];

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  send(data: string | ArrayBuffer) {
    this.sent.push(data);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code: 1000 } as CloseEvent);
  }

  // Test helpers
  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  simulateBinaryMessage(bytes: Uint8Array) {
    this.onmessage?.({ data: bytes.buffer });
  }

  simulateTextMessage(text: string) {
    this.onmessage?.({ data: text });
  }

  simulateClose(code = 1000) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code } as CloseEvent);
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  mockVerify.mockClear();
  (global as any).WebSocket = MockWebSocket;
  // jsdom doesn't ship TextEncoder; polyfill from Node
  if (typeof (global as any).TextEncoder === 'undefined') {
    (global as any).TextEncoder = NodeTextEncoder;
  }
  jest.useFakeTimers();
});

afterEach(() => {
  jest.useRealTimers();
});

// `buildUrl` is async (issue #745 — resolved fresh per connect/retry attempt
// so a single-use ticket embedded in the URL is never replayed). Flush the
// microtask queue so the pending connect finishes creating the WebSocket
// before a test inspects `MockWebSocket.instances`. Fake timers only affect
// macrotasks (setTimeout), not promise microtasks.
async function flushConnect() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

const staticUrl = (url: string) => () => Promise.resolve(url as string | null);

// ── Tests ─────────────────────────────────────────────────────────────────

describe('useTerminalSocket', () => {
  it('starts idle when enabled is false', () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({
        enabled: false,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
      })
    );
    expect(result.current.status).toBe('idle');
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it('transitions connecting → open when socket opens', async () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
      })
    );

    expect(result.current.status).toBe('connecting');
    await flushConnect();
    const ws = MockWebSocket.instances[0];

    act(() => ws.simulateOpen());
    expect(result.current.status).toBe('open');
  });

  it('does not connect, and resolves to error, when buildUrl resolves null', async () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({ enabled: true, buildUrl: async () => null, onData })
    );
    await flushConnect();
    expect(MockWebSocket.instances).toHaveLength(0);
    expect(result.current.status).toBe('error');
  });

  it('calls onData with Uint8Array for binary frames', async () => {
    const onData = jest.fn();
    renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
      })
    );
    await flushConnect();
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    const bytes = new Uint8Array([104, 101, 108, 108, 111]); // "hello"
    act(() => ws.simulateBinaryMessage(bytes));
    const received = onData.mock.calls[0][0] as Uint8Array;
    expect(Array.from(received)).toEqual(Array.from(bytes));
  });

  it('calls onData with encoded bytes for text frames', async () => {
    const onData = jest.fn();
    renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
      })
    );
    await flushConnect();
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    act(() => ws.simulateTextMessage('hi'));
    const expected = new TextEncoder().encode('hi');
    expect(onData).toHaveBeenCalledWith(expected);
  });

  it('sendInput sends data when open', async () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
      })
    );
    await flushConnect();
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    act(() => result.current.sendInput('ls\n'));
    expect(ws.sent).toContain('ls\n');
  });

  it('sendResize sends JSON resize event', async () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
      })
    );
    await flushConnect();
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    act(() => result.current.sendResize(120, 40));
    expect(ws.sent).toContain(JSON.stringify({ type: 'resize', cols: 120, rows: 40 }));
  });

  it('reconnects with backoff on close (up to maxRetries)', async () => {
    const onData = jest.fn();
    renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
        maxRetries: 2,
        retryDelay: 500,
      })
    );
    await flushConnect();

    // First connection opens then closes
    const ws1 = MockWebSocket.instances[0];
    act(() => ws1.simulateOpen());
    act(() => ws1.simulateClose());
    expect(MockWebSocket.instances).toHaveLength(1);

    // Retry 1 after 500ms
    act(() => jest.advanceTimersByTime(500));
    await flushConnect();
    expect(MockWebSocket.instances).toHaveLength(2);

    const ws2 = MockWebSocket.instances[1];
    act(() => ws2.simulateClose());

    // Retry 2 after 1000ms (doubled)
    act(() => jest.advanceTimersByTime(1000));
    await flushConnect();
    expect(MockWebSocket.instances).toHaveLength(3);

    // After maxRetries exhausted, no more reconnects
    const ws3 = MockWebSocket.instances[2];
    act(() => ws3.simulateClose());
    act(() => jest.advanceTimersByTime(2000));
    await flushConnect();
    expect(MockWebSocket.instances).toHaveLength(3);
  });

  it('mints a fresh URL (e.g. a new ticket) on every retry attempt (issue #745)', async () => {
    const onData = jest.fn();
    const buildUrl = jest
      .fn()
      .mockResolvedValueOnce('ws://localhost/ws/sessions/s1/terminal?ticket=tk-1')
      .mockResolvedValueOnce('ws://localhost/ws/sessions/s1/terminal?ticket=tk-2');
    renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl,
        onData,
        maxRetries: 2,
        retryDelay: 500,
      })
    );
    await flushConnect();
    expect(MockWebSocket.instances[0].url).toContain('tk-1');

    const ws1 = MockWebSocket.instances[0];
    act(() => ws1.simulateOpen());
    act(() => ws1.simulateClose());
    act(() => jest.advanceTimersByTime(500));
    await flushConnect();

    expect(MockWebSocket.instances).toHaveLength(2);
    expect(MockWebSocket.instances[1].url).toContain('tk-2');
    expect(buildUrl).toHaveBeenCalledTimes(2);
    const urls = MockWebSocket.instances.map((ws) => ws.url);
    expect(new Set(urls).size).toBe(urls.length);
  });

  it('transitions to error after maxRetries exhausted', async () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
        maxRetries: 1,
        retryDelay: 100,
      })
    );
    await flushConnect();

    const ws1 = MockWebSocket.instances[0];
    act(() => ws1.simulateOpen());
    act(() => ws1.simulateClose());

    act(() => jest.advanceTimersByTime(100));
    await flushConnect();
    const ws2 = MockWebSocket.instances[1];
    act(() => ws2.simulateClose());

    act(() => jest.advanceTimersByTime(200));
    expect(result.current.status).toBe('error');
  });

  it('does not retry on auth failure close codes', async () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
        maxRetries: 3,
        retryDelay: 100,
      })
    );
    await flushConnect();
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());
    // Simulate auth rejection (4001)
    act(() => ws.simulateClose(4001));

    // Should go straight to 'error' — no retry timers
    act(() => jest.advanceTimersByTime(1000));
    expect(MockWebSocket.instances).toHaveLength(1); // no new connection
    expect(result.current.status).toBe('error');
  });

  // The backend denies WS auth before accepting the handshake, so a real
  // browser reports an expired token as 1006 (abnormal), not 4001. The probe
  // must fire on any non-normal close; it self-filters (only a genuine 401
  // redirects), so transient closes still retry.
  it('fires the re-auth probe on an explicit 4001 auth close (#651)', async () => {
    const onData = jest.fn();
    renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
      })
    );
    await flushConnect();
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());
    act(() => ws.simulateClose(4001));

    expect(mockVerify).toHaveBeenCalledTimes(1);
  });

  it('fires the re-auth probe on an abnormal (1006) close', async () => {
    const onData = jest.fn();
    renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
        retryDelay: 100,
      })
    );
    await flushConnect();
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());
    act(() => ws.simulateClose(1006));

    expect(mockVerify).toHaveBeenCalledTimes(1);
  });

  it('does not fire the probe on a clean (1000) close', async () => {
    const onData = jest.fn();
    renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
        retryDelay: 100,
      })
    );
    await flushConnect();
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());
    act(() => ws.simulateClose(1000));

    expect(mockVerify).not.toHaveBeenCalled();
  });

  it('cleans up socket on unmount', async () => {
    const onData = jest.fn();
    const { unmount } = renderHook(() =>
      useTerminalSocket({
        enabled: true,
        buildUrl: staticUrl('ws://localhost/ws/sessions/s1/terminal?ticket=t'),
        onData,
      })
    );
    await flushConnect();
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    const closeSpy = jest.spyOn(ws, 'close');
    unmount();
    expect(closeSpy).toHaveBeenCalled();
  });
});
