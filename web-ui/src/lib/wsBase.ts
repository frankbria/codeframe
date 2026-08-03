/**
 * The single source of truth for the WebSocket base URL (#944).
 *
 * There were two. `AgentTerminal` derived its base from `NEXT_PUBLIC_API_URL`
 * when `NEXT_PUBLIC_WS_URL` was unset; `useAgentChat` hardcoded a loopback
 * address. So a deployment that set only `NEXT_PUBLIC_API_URL` — the documented
 * single-origin setup — got a working terminal and a silently dead chat socket,
 * with no error to explain it.
 *
 * Both reads are written as literal `process.env.NEXT_PUBLIC_*` expressions.
 * Next inlines only that exact textual form at build time; reading the same key
 * off a `process.env` *reference* (a defaulted parameter, a destructure) yields
 * `undefined` in the client bundle — which is where both callers run.
 */
export interface WsEnvOverrides {
  NEXT_PUBLIC_WS_URL?: string;
  NEXT_PUBLIC_API_URL?: string;
}

export function wsBase(overrides: WsEnvOverrides = {}): string {
  const explicit = overrides.NEXT_PUBLIC_WS_URL || process.env.NEXT_PUBLIC_WS_URL;
  if (explicit) return explicit;

  // Derive from the API origin: same host, ws(s) scheme. https -> wss, so a
  // TLS deployment does not fall back to an insecure socket.
  // prettier-ignore -- one line so the env-var-before-fallback CI check matches.
  const apiBase = overrides.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  return apiBase.replace(/^http/, 'ws');
}
