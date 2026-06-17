'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { verifyAuthAfterStreamFailure } from '@/lib/api';

export type SSEStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

export interface UseEventSourceOptions {
  /** URL to connect to. Pass `null` to disable the connection. */
  url: string | null;
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
 * - Auto-connects when `url` transitions from null → string
 * - Auto-disconnects when `url` transitions from string → null
 * - Exponential-backoff reconnect on error (configurable)
 * - Returns current connection status
 * - Cleans up on unmount
 */
export function useEventSource({
  url,
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
  // sequence (reset on a successful open/message) to avoid spamming /users/me.
  const authProbeFiredRef = useRef(false);

  // Keep callback refs stable so effect doesn't re-run on every render
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
    if (!url) {
      // No URL → stay idle (or close if previously open)
      if (sourceRef.current) close();
      else setStatus('idle');
      return;
    }

    const connect = () => {
      setStatus('connecting');

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
          // response (e.g. 401 on an expired `?token=`) rather than a transient
          // network drop. Probe `/users/me` once: a genuine expiry redirects to
          // /login; anything else is left to the retry below (#651).
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
            retryTimerRef.current = setTimeout(connect, delay);
          } else {
            setStatus('error');
          }
        }
      };
    };

    connect();

    return () => {
      close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, withCredentials, maxRetries, retryDelay]);

  return { status, close };
}
