import { TextEncoder as NodeTextEncoder } from 'util';
import { renderHook, act } from '@testing-library/react';
import { useTerminalSocket } from '@/hooks/useTerminalSocket';

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
    this.onclose?.();
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

  simulateClose() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
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

// ── Tests ─────────────────────────────────────────────────────────────────

describe('useTerminalSocket', () => {
  it('starts idle when url is null', () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({ url: null, onData })
    );
    expect(result.current.status).toBe('idle');
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it('transitions connecting → open when socket opens', () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({ url: 'ws://localhost/ws/sessions/s1/terminal?token=t', onData })
    );

    expect(result.current.status).toBe('connecting');
    const ws = MockWebSocket.instances[0];

    act(() => ws.simulateOpen());
    expect(result.current.status).toBe('open');
  });

  it('calls onData with Uint8Array for binary frames', () => {
    const onData = jest.fn();
    renderHook(() =>
      useTerminalSocket({ url: 'ws://localhost/ws/sessions/s1/terminal?token=t', onData })
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    const bytes = new Uint8Array([104, 101, 108, 108, 111]); // "hello"
    act(() => ws.simulateBinaryMessage(bytes));
    const received = onData.mock.calls[0][0] as Uint8Array;
    expect(Array.from(received)).toEqual(Array.from(bytes));
  });

  it('calls onData with encoded bytes for text frames', () => {
    const onData = jest.fn();
    renderHook(() =>
      useTerminalSocket({ url: 'ws://localhost/ws/sessions/s1/terminal?token=t', onData })
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    act(() => ws.simulateTextMessage('hi'));
    const expected = new TextEncoder().encode('hi');
    expect(onData).toHaveBeenCalledWith(expected);
  });

  it('sendInput sends data when open', () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({ url: 'ws://localhost/ws/sessions/s1/terminal?token=t', onData })
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    act(() => result.current.sendInput('ls\n'));
    expect(ws.sent).toContain('ls\n');
  });

  it('sendResize sends JSON resize event', () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({ url: 'ws://localhost/ws/sessions/s1/terminal?token=t', onData })
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    act(() => result.current.sendResize(120, 40));
    expect(ws.sent).toContain(JSON.stringify({ type: 'resize', cols: 120, rows: 40 }));
  });

  it('reconnects with backoff on close (up to maxRetries)', () => {
    const onData = jest.fn();
    renderHook(() =>
      useTerminalSocket({
        url: 'ws://localhost/ws/sessions/s1/terminal?token=t',
        onData,
        maxRetries: 2,
        retryDelay: 500,
      })
    );

    // First connection opens then closes
    const ws1 = MockWebSocket.instances[0];
    act(() => ws1.simulateOpen());
    act(() => ws1.simulateClose());
    expect(MockWebSocket.instances).toHaveLength(1);

    // Retry 1 after 500ms
    act(() => jest.advanceTimersByTime(500));
    expect(MockWebSocket.instances).toHaveLength(2);

    const ws2 = MockWebSocket.instances[1];
    act(() => ws2.simulateClose());

    // Retry 2 after 1000ms (doubled)
    act(() => jest.advanceTimersByTime(1000));
    expect(MockWebSocket.instances).toHaveLength(3);

    // After maxRetries exhausted, no more reconnects
    const ws3 = MockWebSocket.instances[2];
    act(() => ws3.simulateClose());
    act(() => jest.advanceTimersByTime(2000));
    expect(MockWebSocket.instances).toHaveLength(3);
  });

  it('transitions to error after maxRetries exhausted', () => {
    const onData = jest.fn();
    const { result } = renderHook(() =>
      useTerminalSocket({
        url: 'ws://localhost/ws/sessions/s1/terminal?token=t',
        onData,
        maxRetries: 1,
        retryDelay: 100,
      })
    );

    const ws1 = MockWebSocket.instances[0];
    act(() => ws1.simulateOpen());
    act(() => ws1.simulateClose());

    act(() => jest.advanceTimersByTime(100));
    const ws2 = MockWebSocket.instances[1];
    act(() => ws2.simulateClose());

    act(() => jest.advanceTimersByTime(200));
    expect(result.current.status).toBe('error');
  });

  it('cleans up socket on unmount', () => {
    const onData = jest.fn();
    const { unmount } = renderHook(() =>
      useTerminalSocket({ url: 'ws://localhost/ws/sessions/s1/terminal?token=t', onData })
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.simulateOpen());

    const closeSpy = jest.spyOn(ws, 'close');
    unmount();
    expect(closeSpy).toHaveBeenCalled();
  });
});
