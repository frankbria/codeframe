'use client';

import { useEffect, useRef } from 'react';
import { useTerminalSocket, type TerminalSocketStatus } from '@/hooks/useTerminalSocket';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getToken(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('auth_token');
}

function buildWsUrl(sessionId: string): string | null {
  const token = getToken();
  if (!token) return null;
  const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const base =
    process.env.NEXT_PUBLIC_WS_URL ||
    apiBase.replace(/^http/, 'ws');
  return `${base}/ws/sessions/${sessionId}/terminal?token=${encodeURIComponent(token)}`;
}

// ---------------------------------------------------------------------------
// ReconnectingOverlay
// ---------------------------------------------------------------------------

function ReconnectingOverlay({ status }: { status: TerminalSocketStatus }) {
  const message =
    status === 'connecting' ? 'Connecting…' : status === 'error' ? 'Connection failed' : 'Reconnecting…';

  return (
    <div className="absolute inset-0 flex items-center justify-center bg-black/60 z-10">
      <div className="flex flex-col items-center gap-2 text-white/80 text-sm">
        {status !== 'error' && (
          <svg
            className="animate-spin h-5 w-5 text-purple-400"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        )}
        <span>{message}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AgentTerminal
// ---------------------------------------------------------------------------

export interface AgentTerminalProps {
  sessionId: string;
  className?: string;
}

export function AgentTerminal({ sessionId, className }: AgentTerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // Use a ref to hold the xterm Terminal instance across renders
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const terminalRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fitAddonRef = useRef<any>(null);
  const wsUrlRef = useRef<string | null>(null);

  // Build the WS URL once per sessionId (requires client side)
  if (typeof window !== 'undefined' && !wsUrlRef.current) {
    wsUrlRef.current = buildWsUrl(sessionId);
  }

  const { status, sendInput, sendResize } = useTerminalSocket({
    url: wsUrlRef.current,
    onData: (data) => {
      if (terminalRef.current) {
        terminalRef.current.write(data);
      }
    },
  });

  // Mount XTerm on client only (dynamic import to avoid SSR issues with xterm)
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!containerRef.current) return;

    let terminal: any; // eslint-disable-line @typescript-eslint/no-explicit-any
    let fitAddon: any; // eslint-disable-line @typescript-eslint/no-explicit-any
    let resizeObserver: ResizeObserver | null = null;
    let inputDisposer: { dispose: () => void } | null = null;

    // Dynamic import keeps xterm out of the SSR bundle
    Promise.all([import('xterm'), import('xterm-addon-fit')]).then(([{ Terminal }, { FitAddon }]) => {
      if (!containerRef.current) return;

      terminal = new Terminal({
        theme: {
          background: '#0a0a0c',
          cursor: '#a855f7',
          foreground: '#e2e8f0',
        },
        fontFamily: 'monospace',
        fontSize: 14,
        convertEol: true,
        cursorBlink: true,
      });

      fitAddon = new FitAddon();
      terminal.loadAddon(fitAddon);
      terminal.open(containerRef.current);
      fitAddon.fit();

      terminalRef.current = terminal;
      fitAddonRef.current = fitAddon;

      // Forward keystrokes to server
      inputDisposer = terminal.onData((data: string) => {
        sendInput(data);
      });

      // ResizeObserver: refit and notify server on container size change
      resizeObserver = new ResizeObserver(() => {
        try {
          fitAddon.fit();
          sendResize(terminal.cols, terminal.rows);
        } catch {
          // Ignore resize errors during unmount
        }
      });
      resizeObserver.observe(containerRef.current);
    });

    return () => {
      inputDisposer?.dispose();
      resizeObserver?.disconnect();
      terminal?.dispose();
      terminalRef.current = null;
      fitAddonRef.current = null;
    };
    // sendInput and sendResize are stable useCallback references
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const showOverlay = status !== 'open';

  return (
    <div
      className={`relative w-full h-full overflow-hidden bg-[#0a0a0c]${className ? ` ${className}` : ''}`}
    >
      <div ref={containerRef} className="w-full h-full" />
      {showOverlay && <ReconnectingOverlay status={status} />}
    </div>
  );
}
