import { renderHook, act } from '@testing-library/react';
import { useStressTestStream } from '@/hooks/useStressTestStream';

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
  localStorage.clear();
});

const WORKSPACE = '/tmp/test-workspace';

describe('useStressTestStream', () => {
  it('starts idle and does not open a connection', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    expect(result.current.status).toBe('idle');
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('opens a connection on start() and transitions to streaming', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));

    act(() => {
      result.current.start();
    });

    expect(result.current.status).toBe('streaming');
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.latest().url).toContain('/api/v2/prd/stress-test');
    expect(MockEventSource.latest().url).toContain(
      `workspace_path=${encodeURIComponent(WORKSPACE)}`
    );
  });

  it('appends the auth token as a query param when authenticated (#336)', () => {
    localStorage.setItem('auth_token', 'jwt-sse');
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));

    act(() => result.current.start());

    expect(MockEventSource.latest().url).toContain('token=jwt-sse');
  });

  it('omits the token param when not authenticated', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));

    act(() => result.current.start());

    expect(MockEventSource.latest().url).not.toContain('token=');
  });

  it('accumulates human-readable lines from progress events', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());

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

  it('transitions to complete and exposes results', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());

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

  it('transitions to error and captures the message', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());

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

  it('retries with a fresh connection after an error', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());
    act(() => {
      MockEventSource.latest().emit({ type: 'error', message: 'boom' });
    });
    expect(result.current.status).toBe('error');

    act(() => result.current.start());

    expect(result.current.status).toBe('streaming');
    expect(result.current.error).toBeNull();
    // A second, distinct EventSource should have been created.
    expect(MockEventSource.instances.length).toBeGreaterThanOrEqual(2);
    const urls = MockEventSource.instances.map((es) => es.url);
    expect(new Set(urls).size).toBe(urls.length);
  });

  it('reports a transport failure (closed connection, no data) as an error', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());

    // EventSource fails before any `data:` frame and ends up CLOSED.
    act(() => {
      MockEventSource.latest().emitError(MockEventSource.CLOSED);
    });

    expect(result.current.status).toBe('error');
    expect(result.current.error).toMatch(/connection to the stress-test stream failed/i);
  });

  it('ignores transient (non-closed) connection errors while streaming', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());

    // A transient error where the browser will reconnect (readyState CONNECTING).
    act(() => {
      MockEventSource.latest().emitError(MockEventSource.CONNECTING);
    });

    expect(result.current.status).toBe('streaming');
    expect(result.current.error).toBeNull();
  });

  it('does not overwrite a backend error event with a transport error', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());

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

  it('fails fast (no connection) when workspacePath is null', () => {
    const { result } = renderHook(() => useStressTestStream(null));

    act(() => result.current.start());

    expect(result.current.status).toBe('error');
    expect(result.current.error).toMatch(/no workspace selected/i);
    expect(MockEventSource.instances).toHaveLength(0);
  });

  it('reset() closes the connection and returns to idle', () => {
    const { result } = renderHook(() => useStressTestStream(WORKSPACE));
    act(() => result.current.start());
    const es = MockEventSource.latest();

    act(() => result.current.reset());

    expect(result.current.status).toBe('idle');
    expect(result.current.lines).toEqual([]);
    expect(es.readyState).toBe(MockEventSource.CLOSED);
  });
});
