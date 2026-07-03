'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { verifyAuthAfterStreamFailure } from '@/lib/api';

export type SSEStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

export interface UseEventSourceOptions {
  /** Whether the connection should be open. Toggling `false` → `true`
   * (re)connects; `true` → `false` closes it. */
  enabled: boolean;
  /**
   * Extra identity for "what to connect to", independent of `enabled`.
   * Change this value (e.g. a task id, or a counter bumped on retry) to
   * force a fresh (re)connect even while `enabled` stays `true` — needed
   * because `buildUrl` is a function `useEventSource` cannot diff on its
   * own to detect that the desired connection target changed.
   */
  connectionKey?: string | number;
  /**
   * Async URL builder, invoked fresh for the initial connect AND every
   * internal retry attempt. Use this instead of a static URL whenever the
   * URL embeds a single-use credential (e.g. a stream ticket, issue #745) —
   * a plain string would replay an already-consumed credential on retry.
   * Resolving to `null` aborts the attempt (status becomes `'error'`).
   */
  buildUrl: () => Promise<string | null>;
  /** Called for each SSE `message` event (event.data is the raw string). */
  onMessage?: (data: string) => void;
  /** Called when the connection opens. */
  onOpen?: () => void;
  /** Called when the connection encounters an error. */
  onError?: (event: Event) => void;
  /** Whether to add `withCredentials: true` (sends cookies cross-origin). */
  withCredentials?: boolean;
  /**
   * Max automatic reconnect attempts after an error.
   * Set to 0 to disable reconnection.  Defaults to 3.
   */
  maxRetries?: number;
  /** Delay (ms) between reconnect attempts. Doubles each retry. Defaults to 1000. */
  retryDelay?: number;
}

/**
 * Generic hook that manages an `EventSource` (SSE) connection.
 *
 * Features:
 * - Auto-connects when `enabled` transitions false → true (or `connectionKey`
 *   changes while already enabled)
 * - Auto-disconnects when `enabled` transitions true → false
 * - Re-resolves `buildUrl` for every connect AND every retry, so a single-use
 *   credential embedded in the URL is never replayed
 * - Exponential-backoff reconnect on error (configurable)
 * - Returns current connection status
 * - Cleans up on unmount
 */
export function useEventSource({
  enabled,
  connectionKey,
  buildUrl,
  onMessage,
  onOpen,
  onError,
  withCredentials = false,
  maxRetries = 3,
  retryDelay = 1000,
}: UseEventSourceOptions) {
  const [status, setStatus] = useState<SSEStatus>('idle');
  const sourceRef = useRef<EventSource | null>(null);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Fire the token-expiry re-auth probe at most once per connection attempt
  // sequence (reset on a successful message) to avoid spamming the auth probe.
  const authProbeFiredRef = useRef(false);

  // Keep callback refs stable so effect doesn't re-run on every render
  const buildUrlRef = useRef(buildUrl);
  buildUrlRef.current = buildUrl;
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onOpenRef = useRef(onOpen);
  onOpenRef.current = onOpen;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;

  const close = useCallback(() => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    if (sourceRef.current) {
      sourceRef.current.close();
      sourceRef.current = null;
    }
    retriesRef.current = 0;
    authProbeFiredRef.current = false;
    setStatus('closed');
  }, []);

  useEffect(() => {
    if (!enabled) {
      // Disabled → stay idle (or close if previously open)
      if (sourceRef.current) close();
      else setStatus('idle');
      return;
    }

    // Guards a `buildUrl` resolution racing against unmount/re-run (e.g. the
    // effect cleaned up while a ticket fetch was still in flight).
    let cancelled = false;

    const connect = async () => {
      setStatus('connecting');

      const url = await buildUrlRef.current();
      if (cancelled) return;
      if (!url) {
        setStatus('error');
        return;
      }

      const es = new EventSource(url, { withCredentials });
      sourceRef.current = es;

      es.onopen = () => {
        setStatus('open');
        onOpenRef.current?.();
      };

      es.onmessage = (event) => {
        // Reset retries after a successful message (NOT on open) to prevent
        // infinite reconnect loops when the server accepts then immediately
        // closes the connection. The auth-probe guard re-arms on the same
        // signal so a genuinely re-established stream can probe again (#651).
        retriesRef.current = 0;
        authProbeFiredRef.current = false;
        onMessageRef.current?.(event.data);
      };

      es.onerror = (event) => {
        onErrorRef.current?.(event);

        // EventSource auto-reconnects on transient errors, but if readyState
        // is CLOSED the browser gave up — we handle retries ourselves.
        if (es.readyState === EventSource.CLOSED) {
          // A CLOSED EventSource means the browser received an HTTP error
          // response (e.g. 401 on an expired/consumed `?ticket=`) rather than
          // a transient network drop. Probe the auth endpoint once: a
          // genuine expiry redirects to /login; anything else is left to the
          // retry below (#651).
          if (!authProbeFiredRef.current) {
            authProbeFiredRef.current = true;
            void verifyAuthAfterStreamFailure();
          }

          es.close();
          sourceRef.current = null;

          if (retriesRef.current < maxRetries) {
            const delay = retryDelay * 2 ** retriesRef.current;
            retriesRef.current += 1;
            setStatus('connecting');
            // Tickets are single-use — re-run `connect()` (not a bare
            // reconnect to the same URL) so retries mint a fresh one via
            // `buildUrlRef.current()` instead of replaying the consumed one.
            retryTimerRef.current = setTimeout(() => {
              void connect();
            }, delay);
          } else {
            setStatus('error');
          }
        }
      };
    };

    void connect();

    return () => {
      cancelled = true;
      close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, connectionKey, withCredentials, maxRetries, retryDelay]);

  return { status, close };
}
