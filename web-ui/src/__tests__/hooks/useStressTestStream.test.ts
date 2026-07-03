import { renderHook, act, waitFor } from '@testing-library/react';
import { useStressTestStream } from '@/hooks/useStressTestStream';
import { fetchStreamTicket } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  fetchStreamTicket: jest.fn(),
  verifyAuthAfterStreamFailure: jest.fn(),
}));

const mockFetchTicket = fetchStreamTicket as jest.MockedFunction<
  typeof fetchStreamTicket
>;

// ── EventSource mock ──────────────────────────────────────────────────────

class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  static instances: MockEventSource[] = [];

  url: string;
  readyState: number = MockEventSource.CONNECTING;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {
    this.readyState = MockEventSource.CLOSED;
  }

  // Test helpers
  emit(payload: unknown) {
    this.onmessage?.({ data: JSON.stringify(payload) });
  }

  /** Simulate a transport-level error. Pass the resulting readyState. */
  emitError(readyState: number = MockEventSource.CLOSED) {
    this.readyState = readyState;
    this.onerror?.({ target: this });
  }

  static latest(): MockEventSource {
    return MockEventSource.instances[MockEventSource.instances.length - 1];
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  (global as unknown as { EventSource: unknown }).EventSource = MockEventSource;
  mockFetchTicket.mockReset();
  mockFetchTicket.mockResolvedValue('tk-default');
});

const WORKSPACE = '/tmp/test-workspace';

/** Wait for the (async, ticket-fetching) connect to produce N instances. */
async function waitForInstanceCount(n: number) {
  await waitFor(() => expect(MockEventSource.instances).toHaveLength(n));
}

describe('useStressTestStream', () => {
  it('starts idle and does not open a connection', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    expect(result.current.status).toBe('idle');
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('opens a connection on start() and transitions to streaming', async () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));

    act(() => {
      result.current.start();
    });

    expect(result.current.status).toBe('streaming');
    await waitForInstanceCount(1);
    expect(MockEventSource.latest().url).toContain('/api/v2/prd/stress-test');
    expect(MockEventSource.latest().url).toContain(
      `workspace_path=${encodeURIComponent(WORKSPACE)}`
    );
  });

  it('appends a stream ticket as `?ticket=` (issue #745)', async () => {
    mockFetchTicket.mockResolvedValue('tk-sse');
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));

    act(() => result.current.start());

    await waitForInstanceCount(1);
    expect(MockEventSource.latest().url).toContain('ticket=tk-sse');
    expect(MockEventSource.latest().url).not.toContain('token=');
  });

  it('falls back to the bare URL (no ticket, no token) when the ticket fetch fails', async () => {
    mockFetchTicket.mockResolvedValue(null);
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));

    act(() => result.current.start());

    await waitForInstanceCount(1);
    expect(MockEventSource.latest().url).not.toContain('ticket=');
    expect(MockEventSource.latest().url).not.toContain('token=');
  });

  it('accumulates human-readable lines from progress events', async () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());
    await waitForInstanceCount(1);

    act(() => {
      MockEventSource.latest().emit({
        type: 'goals_extracted',
        goals: ['Auth', 'Invoicing', 'Export'],
      });
    });
    act(() => {
      MockEventSource.latest().emit({
        type: 'goal_analyzed',
        goal: 'Auth',
        classification: 'ambiguous',
        ambiguities_so_far: 1,
      });
    });

    expect(result.current.lines).toEqual([
      '✓ Extracted 3 goals',
      '⚠ Auth — ambiguous',
    ]);
    expect(result.current.status).toBe('streaming');
  });

  it('transitions to complete and exposes results', async () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());
    await waitForInstanceCount(1);

    const ambiguities = [
      {
        id: 'amb-1',
        label: 'AUTH SCOPE',
        source_node_title: 'User Authentication',
        questions: ['Email/password or OAuth?'],
        recommendation: 'Add an auth section',
        severity: 'blocking' as const,
        resolved_answer: null,
      },
    ];

    act(() => {
      MockEventSource.latest().emit({
        type: 'complete',
        ambiguity_count: 2,
        ambiguities,
        tech_spec_markdown: '# Technical Specification',
        ambiguity_report: 'PRD Stress Test — 2 ambiguities found',
      });
    });

    expect(result.current.status).toBe('complete');
    expect(result.current.result).toEqual({
      ambiguityCount: 2,
      ambiguities,
      techSpecMarkdown: '# Technical Specification',
      ambiguityReport: 'PRD Stress Test — 2 ambiguities found',
    });
    // Connection should be closed on completion to avoid a reconnect loop.
    expect(MockEventSource.latest().readyState).toBe(MockEventSource.CLOSED);
  });

  it('transitions to error and captures the message', async () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());
    await waitForInstanceCount(1);

    act(() => {
      MockEventSource.latest().emit({
        type: 'error',
        message: 'ANTHROPIC_API_KEY environment variable required.',
      });
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe(
      'ANTHROPIC_API_KEY environment variable required.'
    );
  });

  it('retries with a fresh connection and a fresh ticket after an error', async () => {
    mockFetchTicket.mockResolvedValueOnce('tk-1').mockResolvedValueOnce('tk-2');
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());
    await waitForInstanceCount(1);
    act(() => {
      MockEventSource.latest().emit({ type: 'error', message: 'boom' });
    });
    expect(result.current.status).toBe('error');

    act(() => result.current.start());

    expect(result.current.status).toBe('streaming');
    expect(result.current.error).toBeNull();
    // A second, distinct EventSource should have been created, minted with a
    // fresh ticket (single-use — reusing the first would 401 on replay).
    await waitForInstanceCount(2);
    expect(MockEventSource.instances[0].url).toContain('ticket=tk-1');
    expect(MockEventSource.instances[1].url).toContain('ticket=tk-2');
    const urls = MockEventSource.instances.map((es) => es.url);
    expect(new Set(urls).size).toBe(urls.length);
    expect(mockFetchTicket).toHaveBeenCalledTimes(2);
  });

  it('reports a transport failure (closed connection, no data) as an error', async () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());
    await waitForInstanceCount(1);

    // EventSource fails before any `data:` frame and ends up CLOSED.
    act(() => {
      MockEventSource.latest().emitError(MockEventSource.CLOSED);
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toMatch(/connection to the stress-test stream failed/i);
  });

  it('ignores transient (non-closed) connection errors while streaming', async () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());
    await waitForInstanceCount(1);

    // A transient error where the browser will reconnect (readyState CONNECTING).
    act(() => {
      MockEventSource.latest().emitError(MockEventSource.CONNECTING);
    });

    expect(result.current.status).toBe('streaming');
    expect(result.current.error).toBeNull();
  });

  it('does not overwrite a backend error event with a transport error', async () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());
    await waitForInstanceCount(1);

    act(() => {
      MockEventSource.latest().emit({ type: 'error', message: 'boom from server' });
    });
    // Server then closes the connection, firing onerror — must not clobber.
    act(() => {
      MockEventSource.latest().emitError(MockEventSource.CLOSED);
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toBe('boom from server');
  });

  it('fails fast (no connection) when workspacePath is null', async () => {
    const { result } = renderHook(() => useStressTestStream(null));

    act(() => result.current.start());

    expect(result.current.status).toBe('error');
    expect(result.current.error).toMatch(/no workspace selected/i);
    expect(mockFetchTicket).not.toHaveBeenCalled();
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('reset() closes the connection and returns to idle', async () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());
    await waitForInstanceCount(1);
    const es = MockEventSource.latest();

    act(() => result.current.reset());

    expect(result.current.status).toBe('idle');
    expect(result.current.lines).toEqual([]);
    expect(es.readyState).toBe(MockEventSource.CLOSED);
  });
});
