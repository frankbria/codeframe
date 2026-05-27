'use client';

import { useCallback, useRef, useState } from 'react';
import { useEventSource } from './useEventSource';
import type { StressTestEvent } from '@/types';

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
  // Tracks whether a terminal data event (complete/error) was received, so a
  // transport-level error fired afterward (e.g. the server closing the stream)
  // is not misreported as a connection failure.
  const terminalRef = useRef(false);

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
        terminalRef.current = true;
        setStatus('complete');
        // Server closes after this; close ourselves to avoid a reconnect loop.
        closeRef.current();
        break;
      }
      case 'error':
        terminalRef.current = true;
        setError(event.message);
        setStatus('error');
        closeRef.current();
        break;
    }
  }, []);

  // Surface transport-level failures (server down, 404/CORS, dropped
  // connection) that arrive without any `data:` frame. Without this the modal
  // would stay on "Analyzing PRD..." forever. Only act on a CLOSED connection
  // so the browser's own transient-reconnect attempts aren't reported as
  // failures, and only when no terminal data event has been received.
  const handleError = useCallback((event: Event) => {
    if (terminalRef.current) return;
    const es = event.target as EventSource | null;
    if (es && es.readyState !== EventSource.CLOSED) return;
    setError(
      (prev) =>
        prev ?? 'Connection to the stress-test stream failed. Please try again.'
    );
    setStatus('error');
  }, []);

  const { close } = useEventSource({
    url,
    onMessage: handleMessage,
    onError: handleError,
    // The stress-test is a one-shot stream; don't auto-reconnect when the
    // server closes the connection on completion.
    maxRetries: 0,
  });
  closeRef.current = close;

  const start = useCallback(() => {
    terminalRef.current = false;
    setLines([]);
    setResult(null);
    setError(null);
    if (!workspacePath) {
      // No URL can be built — fail fast instead of hanging in 'streaming'.
      setError('No workspace selected.');
      setStatus('error');
      return;
    }
    setStatus('streaming');
    setRunId((id) => id + 1);
    setActive(true);
  }, [workspacePath]);

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
