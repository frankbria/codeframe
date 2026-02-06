import { renderHook, act } from '@testing-library/react';
import { useTaskStream } from '@/hooks/useTaskStream';
import type { ProgressEvent, CompletionEvent, OutputEvent, ErrorEvent } from '@/hooks/useTaskStream';

// Mock useEventSource
const mockClose = jest.fn();
let capturedOnMessage: ((data: string) => void) | undefined;

jest.mock('@/hooks/useEventSource', () => ({
  useEventSource: ({ onMessage }: { url: string | null; onMessage?: (data: string) => void }) => {
    capturedOnMessage = onMessage;
    return { status: 'open' as const, close: mockClose };
  },
}));

describe('useTaskStream', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    capturedOnMessage = undefined;
  });

  it('returns idle status when taskId is null', () => {
    const { result } = renderHook(() =>
      useTaskStream({ taskId: null, workspacePath: null })
    );
    expect(result.current.lastEvent).toBeNull();
  });

  it('dispatches progress events to onProgress callback', () => {
    const onProgress = jest.fn();
    renderHook(() =>
      useTaskStream({ taskId: 'task-1', workspacePath: '/tmp/ws', onProgress })
    );

    const event: ProgressEvent = {
      event_type: 'progress',
      task_id: 'task-1',
      timestamp: '2026-01-15T10:00:00Z',
      phase: 'planning',
      step: 1,
      total_steps: 5,
      message: 'Creating plan...',
    };

    act(() => {
      capturedOnMessage?.(JSON.stringify(event));
    });

    expect(onProgress).toHaveBeenCalledWith(
      expect.objectContaining({ event_type: 'progress', phase: 'planning' })
    );
  });

  it('dispatches completion events to onComplete callback', () => {
    const onComplete = jest.fn();
    renderHook(() =>
      useTaskStream({ taskId: 'task-1', workspacePath: '/tmp/ws', onComplete })
    );

    const event: CompletionEvent = {
      event_type: 'completion',
      task_id: 'task-1',
      timestamp: '2026-01-15T10:05:00Z',
      status: 'completed',
      duration_seconds: 120.5,
      files_modified: ['src/main.py'],
    };

    act(() => {
      capturedOnMessage?.(JSON.stringify(event));
    });

    expect(onComplete).toHaveBeenCalledWith(
      expect.objectContaining({ event_type: 'completion', status: 'completed' })
    );
  });

  it('dispatches output events to onOutput callback', () => {
    const onOutput = jest.fn();
    renderHook(() =>
      useTaskStream({ taskId: 'task-1', workspacePath: '/tmp/ws', onOutput })
    );

    const event: OutputEvent = {
      event_type: 'output',
      task_id: 'task-1',
      timestamp: '2026-01-15T10:01:00Z',
      stream: 'stdout',
      line: 'Running tests...',
    };

    act(() => {
      capturedOnMessage?.(JSON.stringify(event));
    });

    expect(onOutput).toHaveBeenCalledWith(
      expect.objectContaining({ event_type: 'output', stream: 'stdout' })
    );
  });

  it('dispatches error events to onError callback', () => {
    const onError = jest.fn();
    renderHook(() =>
      useTaskStream({ taskId: 'task-1', workspacePath: '/tmp/ws', onError })
    );

    const event: ErrorEvent = {
      event_type: 'error',
      task_id: 'task-1',
      timestamp: '2026-01-15T10:03:00Z',
      error: 'Module not found',
      error_type: 'ImportError',
    };

    act(() => {
      capturedOnMessage?.(JSON.stringify(event));
    });

    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ event_type: 'error', error: 'Module not found' })
    );
  });

  it('calls onEvent for every event type', () => {
    const onEvent = jest.fn();
    renderHook(() =>
      useTaskStream({ taskId: 'task-1', workspacePath: '/tmp/ws', onEvent })
    );

    act(() => {
      capturedOnMessage?.(
        JSON.stringify({
          event_type: 'heartbeat',
          task_id: 'task-1',
          timestamp: '2026-01-15T10:00:00Z',
        })
      );
    });

    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ event_type: 'heartbeat' })
    );
  });

  it('updates lastEvent on each message', () => {
    const { result } = renderHook(() =>
      useTaskStream({ taskId: 'task-1', workspacePath: '/tmp/ws' })
    );

    expect(result.current.lastEvent).toBeNull();

    act(() => {
      capturedOnMessage?.(
        JSON.stringify({
          event_type: 'progress',
          task_id: 'task-1',
          timestamp: '2026-01-15T10:00:00Z',
          phase: 'execution',
          step: 2,
          total_steps: 5,
          message: 'Step 2...',
        })
      );
    });

    expect(result.current.lastEvent?.event_type).toBe('progress');
  });

  it('ignores malformed JSON messages', () => {
    const onEvent = jest.fn();
    renderHook(() =>
      useTaskStream({ taskId: 'task-1', workspacePath: '/tmp/ws', onEvent })
    );

    act(() => {
      capturedOnMessage?.('not valid json');
    });

    expect(onEvent).not.toHaveBeenCalled();
  });

  it('exposes close function', () => {
    const { result } = renderHook(() =>
      useTaskStream({ taskId: 'task-1', workspacePath: '/tmp/ws' })
    );

    result.current.close();
    expect(mockClose).toHaveBeenCalled();
  });
});
