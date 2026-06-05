/**
 * Covers the auth-token query param wiring for the task execution SSE stream
 * (issue #336). EventSource cannot send an Authorization header, so the JWT
 * must ride along as `?token=`.
 */
import { renderHook } from '@testing-library/react';
import { useTaskStream } from '@/hooks/useTaskStream';

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
  localStorage.clear();
});

const WORKSPACE = '/tmp/ws';
const TASK = 'task-1';

describe('useTaskStream auth token (#336)', () => {
  it('appends ?token= when authenticated', () => {
    localStorage.setItem('auth_token', 'jwt-task');
    renderHook(() => useTaskStream({ taskId: TASK, workspacePath: WORKSPACE }));
    expect(MockEventSource.latest().url).toContain('token=jwt-task');
    expect(MockEventSource.latest().url).toContain('/api/v2/tasks/task-1/stream');
  });

  it('omits the token param when not authenticated', () => {
    renderHook(() => useTaskStream({ taskId: TASK, workspacePath: WORKSPACE }));
    expect(MockEventSource.latest().url).not.toContain('token=');
  });

  it('does not open a connection when taskId is null', () => {
    renderHook(() => useTaskStream({ taskId: null, workspacePath: WORKSPACE }));
    expect(MockEventSource.instances).toHaveLength(0);
  });
});
