'use client';

import { useCallback, useState } from 'react';
import { useEventSource, type SSEStatus } from './useEventSource';

// ── Event types matching backend ExecutionEvent models ──────────────────

export type ExecutionEventType =
  | 'progress'
  | 'output'
  | 'blocker'
  | 'completion'
  | 'error'
  | 'heartbeat';

export interface BaseExecutionEvent {
  event_type: ExecutionEventType;
  task_id: string;
  timestamp: string;
}

export interface ProgressEvent extends BaseExecutionEvent {
  event_type: 'progress';
  phase: string;
  step: number;
  total_steps: number;
  message: string;
}

export interface OutputEvent extends BaseExecutionEvent {
  event_type: 'output';
  stream: 'stdout' | 'stderr';
  line: string;
}

export interface BlockerEvent extends BaseExecutionEvent {
  event_type: 'blocker';
  blocker_id: number;
  question: string;
  context?: string;
}

export interface CompletionEvent extends BaseExecutionEvent {
  event_type: 'completion';
  status: 'completed' | 'failed' | 'blocked';
  duration_seconds: number;
  files_modified?: string[];
}

export interface ErrorEvent extends BaseExecutionEvent {
  event_type: 'error';
  error: string;
  error_type: string;
  traceback?: string;
}

export interface HeartbeatEvent extends BaseExecutionEvent {
  event_type: 'heartbeat';
}

export type ExecutionEvent =
  | ProgressEvent
  | OutputEvent
  | BlockerEvent
  | CompletionEvent
  | ErrorEvent
  | HeartbeatEvent;

// ── Hook options ────────────────────────────────────────────────────────

export interface UseTaskStreamOptions {
  /** Task ID to stream events for. Pass `null` to disable. */
  taskId: string | null;
  /** Workspace path required by the backend. Pass `null` to disable. */
  workspacePath: string | null;
  /** Called for every execution event (including heartbeats). */
  onEvent?: (event: ExecutionEvent) => void;
  /** Called specifically on progress events. */
  onProgress?: (event: ProgressEvent) => void;
  /** Called on stdout/stderr output events. */
  onOutput?: (event: OutputEvent) => void;
  /** Called when a blocker is created during execution. */
  onBlocker?: (event: BlockerEvent) => void;
  /** Called when execution completes (success, failure, or blocked). */
  onComplete?: (event: CompletionEvent) => void;
  /** Called on execution errors. */
  onError?: (event: ErrorEvent) => void;
}

/**
 * Hook that subscribes to the task execution SSE stream
 * at `GET /api/v2/tasks/{taskId}/stream`.
 *
 * Parses incoming JSON into typed `ExecutionEvent` objects and
 * dispatches them to the appropriate callback.
 *
 * Returns the connection status and the last received event.
 */
export function useTaskStream({
  taskId,
  workspacePath,
  onEvent,
  onProgress,
  onOutput,
  onBlocker,
  onComplete,
  onError,
}: UseTaskStreamOptions) {
  const [lastEvent, setLastEvent] = useState<ExecutionEvent | null>(null);

  // SSE must connect directly to the backend — the Next.js rewrite proxy
  // buffers chunked responses, which prevents SSE events from streaming.
  const sseBase = process.env.NEXT_PUBLIC_SSE_URL || 'http://localhost:8000';
  const url =
    taskId && workspacePath
      ? `${sseBase}/api/v2/tasks/${taskId}/stream?workspace_path=${encodeURIComponent(workspacePath)}`
      : null;

  const handleMessage = useCallback(
    (data: string) => {
      try {
        const event = JSON.parse(data) as ExecutionEvent;
        setLastEvent(event);
        onEvent?.(event);

        switch (event.event_type) {
          case 'progress':
            onProgress?.(event);
            break;
          case 'output':
            onOutput?.(event);
            break;
          case 'blocker':
            onBlocker?.(event);
            break;
          case 'completion':
            onComplete?.(event);
            break;
          case 'error':
            onError?.(event);
            break;
          // heartbeat events are passed to onEvent but have no dedicated callback
        }
      } catch {
        // Ignore malformed messages (e.g. SSE comments)
      }
    },
    [onEvent, onProgress, onOutput, onBlocker, onComplete, onError]
  );

  const { status, close } = useEventSource({
    url,
    onMessage: handleMessage,
  });

  return { status, lastEvent, close };
}
