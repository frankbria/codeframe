/**
 * Content-Security-Policy + hardening headers for the web UI (#657).
 *
 * Defense-in-depth: the JWT lives in localStorage (the EventSource header
 * limitation drove the `?token=` design), so a CSP contains any future XSS by
 * locking down where injected JS can send data. connect-src is built from the
 * SAME build-time env the app uses for its API/WS calls, so it matches the
 * real backend without hardcoding a deploy URL.
 *
 * Required by next.config.js (CommonJS) — keep this file dependency-free.
 */

const DEFAULT_WS_URL = 'ws://localhost:8000';
const AVATAR_HOST = 'https://avatars.githubusercontent.com';

/**
 * Closed allow-list of origins the browser may talk to. 'self' covers the
 * same-origin REST/SSE traffic (NEXT_PUBLIC_API_URL defaults to '' = proxied);
 * the WebSocket hooks dial NEXT_PUBLIC_WS_URL (or the localhost default).
 */
function buildConnectSrc({ apiUrl, wsUrl } = {}) {
  const sources = new Set(["'self'"]);
  if (apiUrl) sources.add(apiUrl);
  sources.add(wsUrl || DEFAULT_WS_URL);
  return Array.from(sources).join(' ');
}

function buildCsp(env = process.env) {
  const connectSrc = buildConnectSrc({
    apiUrl: env.NEXT_PUBLIC_API_URL,
    wsUrl: env.NEXT_PUBLIC_WS_URL,
  });
  // unsafe-eval is only needed by the Next.js dev runtime (React Refresh /
  // eval source maps); production bundles never eval, so it ships dev-only.
  const scriptSrc = env.NODE_ENV === 'development'
    ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
    : "script-src 'self' 'unsafe-inline'";
  return [
    "default-src 'self'",
    // ponytail: 'unsafe-inline' is required by the Next.js App Router without
    // a per-request nonce middleware (a much larger change). Residual risk
    // (#783): with the JWT in localStorage and inline scripts allowed, an
    // injected inline script could read the token — containment comes from
    // connect-src/img-src/object-src below (not script-src), which close off
    // the origins the token could be POSTed/GET'd to. Upgrade path: nonce
    // middleware and/or an httpOnly-cookie token.
    scriptSrc,
    "style-src 'self' 'unsafe-inline'",
    `img-src 'self' data: blob: ${AVATAR_HOST}`,
    "font-src 'self' data:",
    `connect-src ${connectSrc}`,
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "form-action 'self'",
  ].join('; ');
}

function securityHeaders(env = process.env) {
  return [
    { key: 'Content-Security-Policy', value: buildCsp(env) },
    { key: 'X-Content-Type-Options', value: 'nosniff' },
    { key: 'X-Frame-Options', value: 'DENY' },
    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  ];
}

module.exports = { buildCsp, buildConnectSrc, securityHeaders };
