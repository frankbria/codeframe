'use client';

import { useCallback, useRef, useState, useEffect } from 'react';
import {
  useTaskStream,
  type ExecutionEvent,
  type ProgressEvent,
  type CompletionEvent,
} from './useTaskStream';
import { deriveAgentState } from '@/lib/eventStyles';
import type { SSEStatus } from './useEventSource';
import type { UIAgentState } from '@/types';

// ── Public interface ──────────────────────────────────────────────────

export interface ExecutionMonitorState {
  /** All accumulated events (heartbeats included for completeness). */
  events: ExecutionEvent[];
  /** Current agent state derived from the latest non-heartbeat event. */
  agentState: UIAgentState;
  /** Current step number from the latest ProgressEvent. */
  currentStep: number;
  /** Total steps from the latest ProgressEvent. */
  totalSteps: number;
  /** Current phase label (planning, execution, verification, etc.). */
  currentPhase: string;
  /** Human-readable message from the latest ProgressEvent. */
  currentMessage: string;
  /** Files modified during execution (from CompletionEvent.files_modified). */
  changedFiles: string[];
  /** Whether the execution has finished (completed, failed, or blocked). */
  isCompleted: boolean;
  /** Terminal status if completed, otherwise null. */
  completionStatus: 'completed' | 'failed' | 'blocked' | null;
  /** Execution duration in seconds (from CompletionEvent), or null. */
  duration: number | null;
  /** Underlying SSE connection status. */
  sseStatus: SSEStatus;
}

/**
 * Higher-level hook that composes `useTaskStream` and accumulates
 * execution events into a single state object for the Execution Monitor.
 *
 * Uses `useRef` + `requestAnimationFrame` batching to avoid per-event
 * re-renders when events arrive rapidly.
 */
export function useExecutionMonitor(
  taskId: string | null,
  workspacePath: string | null = null
): ExecutionMonitorState & { close: () => void } {
  // ── Refs for accumulation (no re-render per event) ────────────────
  const eventsRef = useRef<ExecutionEvent[]>([]);
  const rafRef = useRef<number | null>(null);
  const sseStatusRef = useRef<SSEStatus>('idle');

  // ── State exposed to consumers ────────────────────────────────────
  const [state, setState] = useState<ExecutionMonitorState>({
    events: [],
    agentState: 'CONNECTING',
    currentStep: 0,
    totalSteps: 0,
    currentPhase: '',
    currentMessage: '',
    changedFiles: [],
    isCompleted: false,
    completionStatus: null,
    duration: null,
    sseStatus: 'idle',
  });

  // Reset accumulated state when taskId changes
  useEffect(() => {
    eventsRef.current = [];
    setState({
      events: [],
      agentState: 'CONNECTING',
      currentStep: 0,
      totalSteps: 0,
      currentPhase: '',
      currentMessage: '',
      changedFiles: [],
      isCompleted: false,
      completionStatus: null,
      duration: null,
      sseStatus: 'idle',
    });
  }, [taskId]);

  // ── Flush accumulated events to state via rAF ─────────────────────
  const scheduleFlush = useCallback(() => {
    if (rafRef.current !== null) return; // already scheduled
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      // Snapshot events and compute derived state
      const events = [...eventsRef.current];
      const lastNonHeartbeat = findLastNonHeartbeat(events);

      let agentState: UIAgentState = lastNonHeartbeat
        ? deriveAgentState(lastNonHeartbeat)
        : 'CONNECTING';

      // Don't let rAF flush overwrite DISCONNECTED state
      if (sseStatusRef.current === 'error' || sseStatusRef.current === 'closed') {
        agentState = 'DISCONNECTED';
      }

      const latestProgress = findLatestProgress(events);
      const completion = findCompletion(events);

      setState((prev) => ({
        ...prev,
        events,
        agentState,
        currentStep: latestProgress?.step ?? prev.currentStep,
        totalSteps: latestProgress?.total_steps ?? prev.totalSteps,
        currentPhase: latestProgress?.phase ?? prev.currentPhase,
        currentMessage: latestProgress?.message ?? prev.currentMessage,
        changedFiles: completion?.files_modified ?? prev.changedFiles,
        isCompleted: completion !== null,
        completionStatus: completion?.status ?? null,
        duration: completion?.duration_seconds ?? null,
      }));
    });
  }, []);

  // Cleanup rAF on unmount
  useEffect(() => {
    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
      }
    };
  }, []);

  // ── Event callbacks ───────────────────────────────────────────────
  const onEvent = useCallback(
    (event: ExecutionEvent) => {
      eventsRef.current = [...eventsRef.current, event];
      scheduleFlush();
    },
    [scheduleFlush]
  );

  // ── Compose useTaskStream ─────────────────────────────────────────
  const { status: sseStatus, close } = useTaskStream({
    taskId,
    workspacePath,
    onEvent,
  });

  // Keep sseStatusRef in sync
  useEffect(() => {
    sseStatusRef.current = sseStatus;
  }, [sseStatus]);

  // Sync SSE status into our state
  useEffect(() => {
    setState((prev) => {
      if (prev.sseStatus === sseStatus) return prev;

      // If SSE transitions to error/closed and we haven't completed,
      // mark as disconnected so the UI can show reconnection state.
      const agentState =
        !prev.isCompleted && (sseStatus === 'error' || sseStatus === 'closed')
          ? 'DISCONNECTED'
          : prev.agentState;

      return { ...prev, sseStatus, agentState };
    });
  }, [sseStatus]);

  return { ...state, sseStatus, close };
}

// ── Helpers ───────────────────────────────────────────────────────────

function findLastNonHeartbeat(
  events: ExecutionEvent[]
): ExecutionEvent | null {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].event_type !== 'heartbeat') return events[i];
  }
  return null;
}

function findLatestProgress(events: ExecutionEvent[]): ProgressEvent | null {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].event_type === 'progress') return events[i] as ProgressEvent;
  }
  return null;
}

function findCompletion(events: ExecutionEvent[]): CompletionEvent | null {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].event_type === 'completion')
      return events[i] as CompletionEvent;
  }
  return null;
}
