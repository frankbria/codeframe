/**
 * Covers the stream-ticket wiring for the task execution SSE stream (issue
 * #745). EventSource cannot send an Authorization header, so a short-lived,
 * single-use ticket rides along as `?ticket=` — replacing the long-lived JWT
 * previously appended as `?token=`.
 */
import { renderHook, waitFor } from '@testing-library/react';
import { useTaskStream } from '@/hooks/useTaskStream';
import { fetchStreamTicket } from '@/lib/api';

jest.mock('@/lib/api', () => ({
  fetchStreamTicket: jest.fn(),
  verifyAuthAfterStreamFailure: jest.fn(),
}));

const mockFetchTicket = fetchStreamTicket as jest.MockedFunction<
  typeof fetchStreamTicket
>;

class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;
  static instances: MockEventSource[] = [];

  url: string;
  readyState = MockEventSource.CONNECTING;
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
  static latest(): MockEventSource {
    return MockEventSource.instances[MockEventSource.instances.length - 1];
  }
}

beforeEach(() => {
  MockEventSource.instances = [];
  (global as unknown as { EventSource: unknown }).EventSource = MockEventSource;
  mockFetchTicket.mockReset();
});

const WORKSPACE = '/tmp/ws';
const TASK = 'task-1';

describe('useTaskStream stream ticket (#745)', () => {
  it('appends ?ticket= when a ticket is available and omits ?token=', async () => {
    mockFetchTicket.mockResolvedValue('tk-1');
    renderHook(() => useTaskStream({ taskId: TASK, workspacePath: WORKSPACE }));

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    expect(MockEventSource.latest().url).toContain('ticket=tk-1');
    expect(MockEventSource.latest().url).not.toContain('token=');
    expect(MockEventSource.latest().url).toContain('/api/v2/tasks/task-1/stream');
  });

  it('falls back to the bare URL (no ticket, no token) when the ticket fetch fails', async () => {
    mockFetchTicket.mockResolvedValue(null);
    renderHook(() => useTaskStream({ taskId: TASK, workspacePath: WORKSPACE }));

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    expect(MockEventSource.latest().url).not.toContain('ticket=');
    expect(MockEventSource.latest().url).not.toContain('token=');
  });

  it('does not open a connection when taskId is null', async () => {
    renderHook(() => useTaskStream({ taskId: null, workspacePath: WORKSPACE }));
    await Promise.resolve();
    expect(MockEventSource.instances).toHaveLength(0);
    expect(mockFetchTicket).not.toHaveBeenCalled();
  });

  it('mints a fresh ticket on reconnect (task id change)', async () => {
    mockFetchTicket.mockResolvedValueOnce('tk-1').mockResolvedValueOnce('tk-2');
    const { rerender } = renderHook(
      ({ taskId }) => useTaskStream({ taskId, workspacePath: WORKSPACE }),
      { initialProps: { taskId: TASK as string | null } }
    );

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(1));
    expect(MockEventSource.latest().url).toContain('ticket=tk-1');

    rerender({ taskId: 'task-2' });

    await waitFor(() => expect(MockEventSource.instances).toHaveLength(2));
    expect(MockEventSource.latest().url).toContain('ticket=tk-2');
    expect(MockEventSource.latest().url).toContain('/api/v2/tasks/task-2/stream');
    expect(mockFetchTicket).toHaveBeenCalledTimes(2);
  });
});
