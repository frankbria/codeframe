/**
 * The single source of truth for the WebSocket base URL (#944).
 *
 * There were two. `AgentTerminal` derived its base from `NEXT_PUBLIC_API_URL`
 * when `NEXT_PUBLIC_WS_URL` was unset; `useAgentChat` hardcoded
 * `ws://localhost:8000`. So a deployment that set only `NEXT_PUBLIC_API_URL` —
 * the documented single-origin setup — got a working terminal and a silently
 * dead chat socket, with no error to explain it.
 */
export function wsBase(env: Record<string, string | undefined> = process.env): string {
  const explicit = env.NEXT_PUBLIC_WS_URL;
  if (explicit) return explicit;

  // Derive from the API origin: same host, ws(s) scheme. https -> wss, so a
  // TLS deployment does not fall back to an insecure socket.
  const apiBase = env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  return apiBase.replace(/^http/, 'ws');
}
