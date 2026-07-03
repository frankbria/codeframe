import { renderHook, act } from '@testing-library/react';
import { useEventSource } from '@/hooks/useEventSource';
import { verifyAuthAfterStreamFailure } from '@/lib/api';

// The SSE re-auth probe (#651) is fired from useEventSource on terminal errors.
jest.mock('@/lib/api', () => ({
  verifyAuthAfterStreamFailure: jest.fn(),
}));
const mockVerify = verifyAuthAfterStreamFailure as jest.MockedFunction<
  typeof verifyAuthAfterStreamFailure
>;

// Mock EventSource
class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  url: string;
  withCredentials: boolean;
  readyState: number = MockEventSource.CONNECTING;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  close = jest.fn();

  constructor(url: string, init?: { withCredentials?: boolean }) {
    this.url = url;
    this.withCredentials = init?.withCredentials ?? false;
    MockEventSource._instances.push(this);
  }

  // Helper for tests to simulate events
  simulateOpen() {
    this.readyState = MockEventSource.OPEN;
    this.onopen?.(new Event('open'));
  }

  simulateMessage(data: string) {
    this.onmessage?.(new MessageEvent('message', { data }));
  }

  simulateError(closed = false) {
    if (closed) this.readyState = MockEventSource.CLOSED;
    this.onerror?.(new Event('error'));
  }

  static _instances: MockEventSource[] = [];
  static reset() {
    MockEventSource._instances = [];
  }
  static latest() {
    return MockEventSource._instances[MockEventSource._instances.length - 1];
  }
}

(global as unknown as { EventSource: typeof MockEventSource }).EventSource = MockEventSource;

// `buildUrl` is async (issue #745 — resolved fresh per connect/retry attempt
// so a single-use credential embedded in the URL is never replayed). Flush
// the microtask queue so the pending connect finishes creating the
// EventSource before a test inspects `MockEventSource._instances`. Fake
// timers only affect macrotasks (setTimeout), not promise microtasks.
async function flushConnect() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

const streamUrl = () => Promise.resolve('/api/stream');

describe('useEventSource', () => {
  beforeEach(() => {
    MockEventSource.reset();
    mockVerify.mockClear();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('starts idle when enabled is false', () => {
    const { result } = renderHook(() =>
      useEventSource({ enabled: false, buildUrl: streamUrl })
    );
    expect(result.current.status).toBe('idle');
    expect(MockEventSource._instances).toHaveLength(0);
  });

  it('connects when enabled is true', async () => {
    renderHook(() => useEventSource({ enabled: true, buildUrl: streamUrl }));
    await flushConnect();
    expect(MockEventSource._instances).toHaveLength(1);
    expect(MockEventSource.latest().url).toBe('/api/stream');
  });

  it('does not connect, and resolves to error, when buildUrl resolves null', async () => {
    const { result } = renderHook(() =>
      useEventSource({ enabled: true, buildUrl: async () => null })
    );
    await flushConnect();
    expect(MockEventSource._instances).toHaveLength(0);
    expect(result.current.status).toBe('error');
  });

  it('transitions to open on successful connection', async () => {
    const { result } = renderHook(() =>
      useEventSource({ enabled: true, buildUrl: streamUrl })
    );
    await flushConnect();

    act(() => {
      MockEventSource.latest().simulateOpen();
    });

    expect(result.current.status).toBe('open');
  });

  it('calls onMessage when data arrives', async () => {
    const onMessage = jest.fn();
    renderHook(() =>
      useEventSource({ enabled: true, buildUrl: streamUrl, onMessage })
    );
    await flushConnect();

    act(() => {
      MockEventSource.latest().simulateOpen();
      MockEventSource.latest().simulateMessage('hello');
    });

    expect(onMessage).toHaveBeenCalledWith('hello');
  });

  it('calls onOpen when connection opens', async () => {
    const onOpen = jest.fn();
    renderHook(() =>
      useEventSource({ enabled: true, buildUrl: streamUrl, onOpen })
    );
    await flushConnect();

    act(() => {
      MockEventSource.latest().simulateOpen();
    });

    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('closes connection when enabled changes to false', async () => {
    const { rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) =>
        useEventSource({ enabled, buildUrl: streamUrl }),
      { initialProps: { enabled: true } }
    );
    await flushConnect();

    const es = MockEventSource.latest();

    rerender({ enabled: false });

    expect(es.close).toHaveBeenCalled();
  });

  it('cleans up on unmount', async () => {
    const { unmount } = renderHook(() =>
      useEventSource({ enabled: true, buildUrl: streamUrl })
    );
    await flushConnect();

    const es = MockEventSource.latest();
    unmount();

    expect(es.close).toHaveBeenCalled();
  });

  it('re-resolves buildUrl on connectionKey change even while enabled stays true', async () => {
    const buildUrl = jest
      .fn()
      .mockResolvedValueOnce('/api/stream?ticket=tk-1')
      .mockResolvedValueOnce('/api/stream?ticket=tk-2');
    const { rerender } = renderHook(
      ({ connectionKey }: { connectionKey: number }) =>
        useEventSource({ enabled: true, connectionKey, buildUrl }),
      { initialProps: { connectionKey: 0 } }
    );
    await flushConnect();
    expect(MockEventSource.latest().url).toBe('/api/stream?ticket=tk-1');

    rerender({ connectionKey: 1 });
    await flushConnect();

    expect(MockEventSource._instances).toHaveLength(2);
    expect(MockEventSource.latest().url).toBe('/api/stream?ticket=tk-2');
    expect(buildUrl).toHaveBeenCalledTimes(2);
  });

  it('retries with exponential backoff on closed error', async () => {
    const { result } = renderHook(() =>
      useEventSource({
        enabled: true,
        buildUrl: streamUrl,
        maxRetries: 2,
        retryDelay: 100,
      })
    );
    await flushConnect();

    // Simulate closed connection error
    act(() => {
      MockEventSource.latest().simulateError(true);
    });

    expect(result.current.status).toBe('connecting');

    // Advance past first retry delay (100ms)
    act(() => {
      jest.advanceTimersByTime(100);
    });
    await flushConnect();

    // Should have created a new EventSource
    expect(MockEventSource._instances).toHaveLength(2);
  });

  it('mints a fresh URL (e.g. a new ticket) on every retry attempt', async () => {
    const buildUrl = jest
      .fn()
      .mockResolvedValueOnce('/api/stream?ticket=tk-1')
      .mockResolvedValueOnce('/api/stream?ticket=tk-2');
    renderHook(() =>
      useEventSource({
        enabled: true,
        buildUrl,
        maxRetries: 2,
        retryDelay: 100,
      })
    );
    await flushConnect();
    expect(MockEventSource.latest().url).toBe('/api/stream?ticket=tk-1');

    act(() => {
      MockEventSource.latest().simulateError(true);
    });
    act(() => {
      jest.advanceTimersByTime(100);
    });
    await flushConnect();

    expect(MockEventSource._instances).toHaveLength(2);
    expect(MockEventSource.latest().url).toBe('/api/stream?ticket=tk-2');
    expect(buildUrl).toHaveBeenCalledTimes(2);
  });

  it('enters error state after max retries', async () => {
    const { result } = renderHook(() =>
      useEventSource({
        enabled: true,
        buildUrl: streamUrl,
        maxRetries: 1,
        retryDelay: 100,
      })
    );
    await flushConnect();

    // First error → retry
    act(() => {
      MockEventSource.latest().simulateError(true);
    });

    act(() => {
      jest.advanceTimersByTime(100);
    });
    await flushConnect();

    // Second error → max retries exceeded
    act(() => {
      MockEventSource.latest().simulateError(true);
    });

    expect(result.current.status).toBe('error');
  });

  it('exhausts the retry budget even when each connection opens before closing (no infinite loop)', async () => {
    const { result } = renderHook(() =>
      useEventSource({ enabled: true, buildUrl: streamUrl, maxRetries: 1, retryDelay: 100 })
    );
    await flushConnect();

    // Open then close WITHOUT a message — opening must not refund the retry
    // budget, otherwise a server that accepts-then-drops loops forever.
    act(() => {
      MockEventSource.latest().simulateOpen();
      MockEventSource.latest().simulateError(true);
    });
    act(() => {
      jest.advanceTimersByTime(100);
    });
    await flushConnect();
    act(() => {
      MockEventSource.latest().simulateOpen();
      MockEventSource.latest().simulateError(true);
    });

    expect(result.current.status).toBe('error');
    expect(MockEventSource._instances).toHaveLength(2); // one retry, then gave up
  });

  // ─── Token-expiry re-auth probe (#651) ─────────────────────────────────

  it('fires the re-auth probe once on a CLOSED (fatal) error', async () => {
    renderHook(() =>
      useEventSource({ enabled: true, buildUrl: streamUrl, maxRetries: 2 })
    );
    await flushConnect();

    act(() => {
      MockEventSource.latest().simulateError(true);
    });

    expect(mockVerify).toHaveBeenCalledTimes(1);
  });

  it('does not fire the probe on a transient (non-CLOSED) error', async () => {
    renderHook(() => useEventSource({ enabled: true, buildUrl: streamUrl }));
    await flushConnect();

    act(() => {
      MockEventSource.latest().simulateError(false);
    });

    expect(mockVerify).not.toHaveBeenCalled();
  });

  it('does not re-fire the probe on repeated CLOSED errors before a reconnect succeeds', async () => {
    renderHook(() =>
      useEventSource({
        enabled: true,
        buildUrl: streamUrl,
        maxRetries: 3,
        retryDelay: 100,
      })
    );
    await flushConnect();

    act(() => {
      MockEventSource.latest().simulateError(true);
    });
    act(() => {
      jest.advanceTimersByTime(100);
    });
    await flushConnect();
    // New EventSource from the reconnect; another fatal error.
    act(() => {
      MockEventSource.latest().simulateError(true);
    });

    expect(mockVerify).toHaveBeenCalledTimes(1);
  });

  it('re-arms the probe after a successful message between failures', async () => {
    renderHook(() =>
      useEventSource({
        enabled: true,
        buildUrl: streamUrl,
        maxRetries: 3,
        retryDelay: 100,
      })
    );
    await flushConnect();

    act(() => {
      MockEventSource.latest().simulateError(true);
    });
    act(() => {
      jest.advanceTimersByTime(100);
    });
    await flushConnect();
    act(() => {
      MockEventSource.latest().simulateOpen();
      MockEventSource.latest().simulateMessage('ok');
      MockEventSource.latest().simulateError(true);
    });

    expect(mockVerify).toHaveBeenCalledTimes(2);
  });
});
