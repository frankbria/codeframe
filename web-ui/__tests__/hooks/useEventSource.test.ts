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

describe('useEventSource', () => {
  beforeEach(() => {
    MockEventSource.reset();
    mockVerify.mockClear();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('starts idle when url is null', () => {
    const { result } = renderHook(() =>
      useEventSource({ url: null })
    );
    expect(result.current.status).toBe('idle');
    expect(MockEventSource._instances).toHaveLength(0);
  });

  it('connects when url is provided', () => {
    renderHook(() =>
      useEventSource({ url: '/api/stream' })
    );
    expect(MockEventSource._instances).toHaveLength(1);
    expect(MockEventSource.latest().url).toBe('/api/stream');
  });

  it('transitions to open on successful connection', () => {
    const { result } = renderHook(() =>
      useEventSource({ url: '/api/stream' })
    );

    act(() => {
      MockEventSource.latest().simulateOpen();
    });

    expect(result.current.status).toBe('open');
  });

  it('calls onMessage when data arrives', () => {
    const onMessage = jest.fn();
    renderHook(() =>
      useEventSource({ url: '/api/stream', onMessage })
    );

    act(() => {
      MockEventSource.latest().simulateOpen();
      MockEventSource.latest().simulateMessage('hello');
    });

    expect(onMessage).toHaveBeenCalledWith('hello');
  });

  it('calls onOpen when connection opens', () => {
    const onOpen = jest.fn();
    renderHook(() =>
      useEventSource({ url: '/api/stream', onOpen })
    );

    act(() => {
      MockEventSource.latest().simulateOpen();
    });

    expect(onOpen).toHaveBeenCalledTimes(1);
  });

  it('closes connection when url changes to null', () => {
    const { rerender } = renderHook(
      ({ url }: { url: string | null }) => useEventSource({ url }),
      { initialProps: { url: '/api/stream' as string | null } }
    );

    const es = MockEventSource.latest();

    rerender({ url: null });

    expect(es.close).toHaveBeenCalled();
  });

  it('cleans up on unmount', () => {
    const { unmount } = renderHook(() =>
      useEventSource({ url: '/api/stream' })
    );

    const es = MockEventSource.latest();
    unmount();

    expect(es.close).toHaveBeenCalled();
  });

  it('retries with exponential backoff on closed error', () => {
    const { result } = renderHook(() =>
      useEventSource({
        url: '/api/stream',
        maxRetries: 2,
        retryDelay: 100,
      })
    );

    // Simulate closed connection error
    act(() => {
      MockEventSource.latest().simulateError(true);
    });

    expect(result.current.status).toBe('connecting');

    // Advance past first retry delay (100ms)
    act(() => {
      jest.advanceTimersByTime(100);
    });

    // Should have created a new EventSource
    expect(MockEventSource._instances).toHaveLength(2);
  });

  it('enters error state after max retries', () => {
    const { result } = renderHook(() =>
      useEventSource({
        url: '/api/stream',
        maxRetries: 1,
        retryDelay: 100,
      })
    );

    // First error → retry
    act(() => {
      MockEventSource.latest().simulateError(true);
    });

    act(() => {
      jest.advanceTimersByTime(100);
    });

    // Second error → max retries exceeded
    act(() => {
      MockEventSource.latest().simulateError(true);
    });

    expect(result.current.status).toBe('error');
  });

  // ─── Token-expiry re-auth probe (#651) ─────────────────────────────────

  it('fires the re-auth probe once on a CLOSED (fatal) error', () => {
    renderHook(() => useEventSource({ url: '/api/stream', maxRetries: 2 }));

    act(() => {
      MockEventSource.latest().simulateError(true);
    });

    expect(mockVerify).toHaveBeenCalledTimes(1);
  });

  it('does not fire the probe on a transient (non-CLOSED) error', () => {
    renderHook(() => useEventSource({ url: '/api/stream' }));

    act(() => {
      MockEventSource.latest().simulateError(false);
    });

    expect(mockVerify).not.toHaveBeenCalled();
  });

  it('does not re-fire the probe on repeated CLOSED errors before a reconnect succeeds', () => {
    renderHook(() =>
      useEventSource({ url: '/api/stream', maxRetries: 3, retryDelay: 100 })
    );

    act(() => {
      MockEventSource.latest().simulateError(true);
    });
    act(() => {
      jest.advanceTimersByTime(100);
    });
    // New EventSource from the reconnect; another fatal error.
    act(() => {
      MockEventSource.latest().simulateError(true);
    });

    expect(mockVerify).toHaveBeenCalledTimes(1);
  });

  it('re-arms the probe after a successful message between failures', () => {
    renderHook(() =>
      useEventSource({ url: '/api/stream', maxRetries: 3, retryDelay: 100 })
    );

    act(() => {
      MockEventSource.latest().simulateError(true);
    });
    act(() => {
      jest.advanceTimersByTime(100);
    });
    act(() => {
      MockEventSource.latest().simulateOpen();
      MockEventSource.latest().simulateMessage('ok');
      MockEventSource.latest().simulateError(true);
    });

    expect(mockVerify).toHaveBeenCalledTimes(2);
  });
});
