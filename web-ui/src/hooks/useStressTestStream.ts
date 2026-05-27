'use client';

import { useCallback, useRef, useState } from 'react';
import { useEventSource } from './useEventSource';

// ── Event types matching the backend stress_test_prd_stream payloads ──────

export type StressTestEventType =
  | 'goals_extracted'
  | 'goal_analyzed'
  | 'complete'
  | 'error';

export interface StressTestGoalsExtractedEvent {
  type: 'goals_extracted';
  goals: string[];
}

export interface StressTestGoalAnalyzedEvent {
  type: 'goal_analyzed';
  goal: string;
  classification: 'atomic' | 'composite' | 'ambiguous';
  ambiguities_so_far: number;
}

export interface StressTestCompleteEvent {
  type: 'complete';
  ambiguity_count: number;
  tech_spec_markdown: string;
  ambiguity_report: string;
}

export interface StressTestErrorEvent {
  type: 'error';
  message: string;
}

export type StressTestEvent =
  | StressTestGoalsExtractedEvent
  | StressTestGoalAnalyzedEvent
  | StressTestCompleteEvent
  | StressTestErrorEvent;

// ── Hook state ────────────────────────────────────────────────────────────

export type StressTestStatus = 'idle' | 'streaming' | 'complete' | 'error';

/** Decomposition results, retained for the results view (issue #562). */
export interface StressTestResultData {
  ambiguityCount: number;
  techSpecMarkdown: string;
  ambiguityReport: string;
}

export interface UseStressTestStreamReturn {
  status: StressTestStatus;
  /** Human-readable progress lines accumulated from incoming events. */
  lines: string[];
  result: StressTestResultData | null;
  error: string | null;
  /** Begin (or restart) the stress-test stream. */
  start: () => void;
  /** Stop streaming and clear all state back to idle. */
  reset: () => void;
}

function classificationIcon(classification: string): string {
  return classification === 'ambiguous' ? '⚠' : '✓';
}

/**
 * Subscribes to the PRD stress-test SSE stream at
 * `GET /api/v2/prd/stress-test`, parsing JSON events into a small state
 * machine (idle → streaming → complete | error) plus human-readable lines.
 *
 * Mirrors `useTaskStream`: connects directly to `NEXT_PUBLIC_SSE_URL`
 * because the Next.js rewrite proxy buffers chunked responses and would
 * prevent SSE events from streaming incrementally.
 */
export function useStressTestStream(
  workspacePath: string | null
): UseStressTestStreamReturn {
  const [status, setStatus] = useState<StressTestStatus>('idle');
  const [lines, setLines] = useState<string[]>([]);
  const [result, setResult] = useState<StressTestResultData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [active, setActive] = useState(false);
  // Bumped on every start() so a retry produces a fresh URL — useEventSource
  // keys off the URL string, so reusing it verbatim would not reconnect.
  const [runId, setRunId] = useState(0);

  // Ref to close() so the message handler can stop the stream on a terminal
  // event without a stale closure (close is created after handleMessage).
  const closeRef = useRef<() => void>(() => {});

  const sseBase = process.env.NEXT_PUBLIC_SSE_URL || 'http://localhost:8000';
  const url =
    active && workspacePath
      ? `${sseBase}/api/v2/prd/stress-test?workspace_path=${encodeURIComponent(workspacePath)}&run=${runId}`
      : null;

  const handleMessage = useCallback((data: string) => {
    let event: StressTestEvent;
    try {
      event = JSON.parse(data) as StressTestEvent;
    } catch {
      // Ignore malformed messages (e.g. SSE comment heartbeats)
      return;
    }

    switch (event.type) {
      case 'goals_extracted': {
        const n = event.goals.length;
        setLines((prev) => [
          ...prev,
          `✓ Extracted ${n} goal${n === 1 ? '' : 's'}`,
        ]);
        break;
      }
      case 'goal_analyzed':
        setLines((prev) => [
          ...prev,
          `${classificationIcon(event.classification)} ${event.goal} — ${event.classification}`,
        ]);
        break;
      case 'complete': {
        const n = event.ambiguity_count;
        setLines((prev) => [
          ...prev,
          `✓ Analysis complete — ${n} ambiguit${n === 1 ? 'y' : 'ies'} found`,
        ]);
        setResult({
          ambiguityCount: event.ambiguity_count,
          techSpecMarkdown: event.tech_spec_markdown,
          ambiguityReport: event.ambiguity_report,
        });
        setStatus('complete');
        // Server closes after this; close ourselves to avoid a reconnect loop.
        closeRef.current();
        break;
      }
      case 'error':
        setError(event.message);
        setStatus('error');
        closeRef.current();
        break;
    }
  }, []);

  const { close } = useEventSource({
    url,
    onMessage: handleMessage,
    // The stress-test is a one-shot stream; don't auto-reconnect when the
    // server closes the connection on completion.
    maxRetries: 0,
  });
  closeRef.current = close;

  const start = useCallback(() => {
    setLines([]);
    setResult(null);
    setError(null);
    setStatus('streaming');
    setRunId((id) => id + 1);
    setActive(true);
  }, []);

  const reset = useCallback(() => {
    close();
    setActive(false);
    setStatus('idle');
    setLines([]);
    setResult(null);
    setError(null);
  }, [close]);

  return { status, lines, result, error, start, reset };
}
