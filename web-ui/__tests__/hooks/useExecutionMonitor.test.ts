import { renderHook, act } from '@testing-library/react';
import { useExecutionMonitor } from '@/hooks/useExecutionMonitor';
import type {
  ProgressEvent,
  CompletionEvent,
  ErrorEvent,
  HeartbeatEvent,
  OutputEvent,
} from '@/hooks/useTaskStream';

// ── Mock useTaskStream ────────────────────────────────────────────────

let capturedOnEvent: ((event: never) => void) | undefined;
let mockSSEStatus = 'open';

jest.mock('@/hooks/useTaskStream', () => ({
  useTaskStream: ({ onEvent }: { taskId: string | null; onEvent?: (event: never) => void }) => {
    capturedOnEvent = onEvent;
    return { status: mockSSEStatus, close: jest.fn() };
  },
}));

// Mock requestAnimationFrame with a queue so callbacks don't race
// with the return value assignment in scheduleFlush.
let rafQueue: FrameRequestCallback[] = [];
let rafId = 0;

function flushRAF() {
  const cbs = [...rafQueue];
  rafQueue = [];
  cbs.forEach((cb) => cb(0));
}

/** Dispatch an event and flush the rAF queue in a single act(). */
function dispatchAndFlush(event: unknown) {
  act(() => {
    capturedOnEvent?.(event as never);
    flushRAF();
  });
}

beforeEach(() => {
  jest.clearAllMocks();
  capturedOnEvent = undefined;
  mockSSEStatus = 'open';
  rafQueue = [];
  rafId = 0;

  jest.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
    rafQueue.push(cb);
    return ++rafId;
  });
  jest.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
});

afterEach(() => {
  jest.restoreAllMocks();
});

// ── Fixtures ──────────────────────────────────────────────────────────

function makeProgressEvent(overrides: Partial<ProgressEvent> = {}): ProgressEvent {
  return {
    event_type: 'progress',
    task_id: 'task-1',
    timestamp: '2026-02-06T10:00:00Z',
    phase: 'execution',
    step: 1,
    total_steps: 5,
    message: 'Running step 1',
    ...overrides,
  };
}

function makeCompletionEvent(overrides: Partial<CompletionEvent> = {}): CompletionEvent {
  return {
    event_type: 'completion',
    task_id: 'task-1',
    timestamp: '2026-02-06T10:05:00Z',
    status: 'completed',
    duration_seconds: 120,
    files_modified: ['src/main.py', 'tests/test_main.py'],
    ...overrides,
  };
}

// ── Tests ─────────────────────────────────────────────────────────────

describe('useExecutionMonitor', () => {
  it('starts with CONNECTING state and empty events', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    expect(result.current.agentState).toBe('CONNECTING');
    expect(result.current.events).toEqual([]);
    expect(result.current.isCompleted).toBe(false);
    expect(result.current.completionStatus).toBeNull();
  });

  it('accumulates events and derives agent state from latest non-heartbeat', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    dispatchAndFlush(makeProgressEvent({ phase: 'planning', step: 1 }));

    expect(result.current.events).toHaveLength(1);
    expect(result.current.agentState).toBe('PLANNING');

    dispatchAndFlush(makeProgressEvent({ phase: 'execution', step: 2 }));

    expect(result.current.events).toHaveLength(2);
    expect(result.current.agentState).toBe('EXECUTING');
  });

  it('tracks progress step and total from latest ProgressEvent', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    dispatchAndFlush(makeProgressEvent({ step: 3, total_steps: 10, message: 'Building' }));

    expect(result.current.currentStep).toBe(3);
    expect(result.current.totalSteps).toBe(10);
    expect(result.current.currentMessage).toBe('Building');
  });

  it('ignores heartbeats for agent state derivation', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    dispatchAndFlush(makeProgressEvent({ phase: 'verification' }));

    expect(result.current.agentState).toBe('VERIFICATION');

    const heartbeat: HeartbeatEvent = {
      event_type: 'heartbeat',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:01:00Z',
    };

    dispatchAndFlush(heartbeat);

    // Heartbeat added to events but state still VERIFICATION
    expect(result.current.events).toHaveLength(2);
    expect(result.current.agentState).toBe('VERIFICATION');
  });

  it('detects completion and stores status and duration', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    dispatchAndFlush(makeCompletionEvent());

    expect(result.current.isCompleted).toBe(true);
    expect(result.current.completionStatus).toBe('completed');
    expect(result.current.duration).toBe(120);
    expect(result.current.agentState).toBe('COMPLETED');
  });

  it('collects changed files from completion event', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    dispatchAndFlush(makeCompletionEvent({ files_modified: ['a.py', 'b.py', 'c.py'] }));

    expect(result.current.changedFiles).toEqual(['a.py', 'b.py', 'c.py']);
  });

  it('derives FAILED state from error events', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    const errorEvent: ErrorEvent = {
      event_type: 'error',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:02:00Z',
      error: 'Module not found',
      error_type: 'ImportError',
    };

    dispatchAndFlush(errorEvent);

    expect(result.current.agentState).toBe('FAILED');
  });

  it('derives BLOCKED state from blocker events', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    dispatchAndFlush({
      event_type: 'blocker',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:02:00Z',
      blocker_id: 42,
      question: 'Which database?',
    });

    expect(result.current.agentState).toBe('BLOCKED');
  });

  it('derives SELF_CORRECTING from self_correction phase', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    dispatchAndFlush(makeProgressEvent({ phase: 'self_correction' }));

    expect(result.current.agentState).toBe('SELF_CORRECTING');
  });

  it('handles output events as EXECUTING state', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    const outputEvent: OutputEvent = {
      event_type: 'output',
      task_id: 'task-1',
      timestamp: '2026-02-06T10:01:00Z',
      stream: 'stdout',
      line: 'Running tests...',
    };

    dispatchAndFlush(outputEvent);

    expect(result.current.agentState).toBe('EXECUTING');
  });

  it('resets state when taskId changes', () => {
    const { result, rerender } = renderHook(
      ({ taskId }) => useExecutionMonitor(taskId),
      { initialProps: { taskId: 'task-1' as string | null } }
    );

    dispatchAndFlush(makeProgressEvent({ step: 5, total_steps: 10 }));

    expect(result.current.events).toHaveLength(1);
    expect(result.current.currentStep).toBe(5);

    // Switch to a different task
    rerender({ taskId: 'task-2' });

    expect(result.current.events).toEqual([]);
    expect(result.current.currentStep).toBe(0);
    expect(result.current.agentState).toBe('CONNECTING');
  });

  it('handles failed completion status', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    dispatchAndFlush(makeCompletionEvent({ status: 'failed' }));

    expect(result.current.isCompleted).toBe(true);
    expect(result.current.completionStatus).toBe('failed');
    expect(result.current.agentState).toBe('FAILED');
  });

  it('handles blocked completion status', () => {
    const { result } = renderHook(() => useExecutionMonitor('task-1'));

    dispatchAndFlush(makeCompletionEvent({ status: 'blocked' }));

    expect(result.current.isCompleted).toBe(true);
    expect(result.current.completionStatus).toBe('blocked');
    expect(result.current.agentState).toBe('BLOCKED');
  });
});
