'use client';

import { useEffect, useRef, useCallback, useState } from 'react';

export type TerminalSocketStatus = 'idle' | 'connecting' | 'open' | 'closed' | 'error';

export interface UseTerminalSocketOptions {
  /** Full WebSocket URL. Pass `null` to disable the connection. */
  url: string | null;
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
 * Mirrors the structure of useEventSource but operates on a WebSocket with
 * binary frames and exposes sendInput/sendResize helpers.
 */
export function useTerminalSocket({
  url,
  onData,
  maxRetries = 3,
  retryDelay = 1000,
}: UseTerminalSocketOptions): UseTerminalSocketReturn {
  const [status, setStatus] = useState<TerminalSocketStatus>('idle');
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep callbacks stable so the effect doesn't re-run on every render
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
    if (!url) {
      if (wsRef.current) close();
      else setStatus('idle');
      return;
    }

    const connect = () => {
      setStatus('connecting');

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

      ws.onclose = () => {
        wsRef.current = null;
        if (retriesRef.current < maxRetries) {
          const delay = retryDelay * 2 ** retriesRef.current;
          retriesRef.current += 1;
          setStatus('connecting');
          retryTimerRef.current = setTimeout(connect, delay);
        } else {
          setStatus('error');
        }
      };
    };

    connect();

    return () => {
      close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, maxRetries, retryDelay]);

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
