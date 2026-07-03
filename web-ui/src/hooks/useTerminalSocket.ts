'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { verifyAuthAfterStreamFailure } from '@/lib/api';

// Normal WebSocket closure (RFC 6455). Anything else is treated as a possible
// auth/expiry failure for the re-auth probe — see onclose below.
const WS_NORMAL_CLOSURE_CODE = 1000;

export type TerminalSocketStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

export interface UseTerminalSocketOptions {
  /** Whether the connection should be open. Toggling `false` → `true`
   * (re)connects; `true` → `false` closes it. */
  enabled: boolean;
  /**
   * Extra identity for "what to connect to", independent of `enabled`.
   * Change this (e.g. a session id) to force a fresh (re)connect even while
   * `enabled` stays `true` — needed because `buildUrl` is a function this
   * hook cannot diff on its own to detect a changed connection target.
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
  /** Called with raw bytes received from the server. */
  onData: (data: Uint8Array) => void;
  /** Max automatic reconnect attempts after a disconnect. Defaults to 3. */
  maxRetries?: number;
  /** Base delay (ms) between reconnect attempts (doubles each retry). Defaults to 1000. */
  retryDelay?: number;
}

export interface UseTerminalSocketReturn {
  status: TerminalSocketStatus;
  /** Send raw keystroke data to the server. */
  sendInput: (data: string) => void;
  /** Send a terminal resize event to the server. */
  sendResize: (cols: number, rows: number) => void;
}

/**
 * Custom hook that manages a WebSocket connection for an interactive terminal.
 *
 * Mirrors `useEventSource`'s `{enabled, connectionKey, buildUrl}` shape:
 * `buildUrl` is re-resolved for the initial connect AND every internal retry,
 * so a single-use credential embedded in the URL (issue #745) is never
 * replayed against an already-consumed ticket.
 */
export function useTerminalSocket({
  enabled,
  connectionKey,
  buildUrl,
  onData,
  maxRetries = 3,
  retryDelay = 1000,
}: UseTerminalSocketOptions): UseTerminalSocketReturn {
  const [status, setStatus] = useState<TerminalSocketStatus>('idle');
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep callbacks stable so the effect doesn't re-run on every render
  const buildUrlRef = useRef(buildUrl);
  buildUrlRef.current = buildUrl;
  const onDataRef = useRef(onData);
  onDataRef.current = onData;

  const close = useCallback(() => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onopen = null;
      wsRef.current.onmessage = null;
      wsRef.current.onerror = null;
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    retriesRef.current = 0;
    setStatus('closed');
  }, []);

  useEffect(() => {
    if (!enabled) {
      if (wsRef.current) close();
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

      const ws = new WebSocket(url);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onopen = () => {
        retriesRef.current = 0;
        setStatus('open');
      };

      ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          onDataRef.current(new Uint8Array(event.data));
        } else if (typeof event.data === 'string') {
          onDataRef.current(new TextEncoder().encode(event.data));
        }
      };

      ws.onerror = () => {
        // onerror is always followed by onclose; handle retry there
      };

      ws.onclose = (event) => {
        wsRef.current = null;
        // A non-normal close may be an expired token. The backend rejects auth
        // *before* accepting the WS handshake, so browsers report it as 1006
        // (abnormal closure), not the server's 4001 — key off "not a clean
        // close" rather than a specific code. The probe only redirects on a
        // genuine 401; transient closes still recover via the retry below (#651).
        if (event.code !== WS_NORMAL_CLOSURE_CODE) {
          void verifyAuthAfterStreamFailure();
        }
        // Auth/authz rejections (4001, 4003, 4004, 4008) are permanent — retrying
        // would loop endlessly with the same credentials. Go straight to error.
        const isPermanentFailure =
          event.code === 4001 || event.code === 4003 ||
          event.code === 4004 || event.code === 4008;
        if (!isPermanentFailure && retriesRef.current < maxRetries) {
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
      };
    };

    void connect();

    return () => {
      cancelled = true;
      close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, connectionKey, maxRetries, retryDelay]);

  const sendInput = useCallback((data: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  const sendResize = useCallback((cols: number, rows: number) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'resize', cols, rows }));
    }
  }, []);

  return { status, sendInput, sendResize };
}
