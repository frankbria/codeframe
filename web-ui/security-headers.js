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

/**
 * Build the script-src directive.
 *
 * With a per-request nonce (the production path, set by proxy.ts) this is
 * `'self' 'nonce-<n>' 'strict-dynamic'` and contains NO 'unsafe-inline', so an
 * injected inline script simply does not execute — which is what protects the
 * localStorage JWT (#936). 'strict-dynamic' lets Next.js's nonced bootstrap
 * load the chunks it needs without enumerating them.
 *
 * Browsers that understand 'strict-dynamic' ignore 'self' for scripts; it is
 * kept for older ones, which then fall back to a host allow-list rather than
 * to nothing.
 *
 * Without a nonce we cannot serve a working App Router page, so the nonce-less
 * form keeps 'unsafe-inline'. That form must only ever reach responses that are
 * not HTML documents — see next.config.js.
 */
function buildScriptSrc({ nonce, isDev } = {}) {
  // unsafe-eval is only needed by the Next.js dev runtime (React Refresh /
  // eval source maps); production bundles never eval, so it ships dev-only.
  const devEval = isDev ? " 'unsafe-eval'" : '';
  if (nonce) {
    return `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${devEval}`;
  }
  return `script-src 'self' 'unsafe-inline'${devEval}`;
}

function buildCsp(env = process.env, { nonce } = {}) {
  const connectSrc = buildConnectSrc({
    apiUrl: env.NEXT_PUBLIC_API_URL,
    wsUrl: env.NEXT_PUBLIC_WS_URL,
  });
  const scriptSrc = buildScriptSrc({
    nonce,
    isDev: env.NODE_ENV === 'development',
  });
  return [
    "default-src 'self'",
    // script-src carries a per-request nonce in production (#936), so an
    // injected inline script does not run and cannot read the localStorage
    // JWT. That closes the top-level-navigation exfil channel too
    // (`window.location = attacker + token`), which no CSP directive could
    // block once the script was already executing — the residual risk this
    // comment used to concede (#783).
    //
    // style-src deliberately keeps 'unsafe-inline': Tailwind and React set
    // style attributes directly, and a stolen *style* is not a stolen session.
    // The threat this addresses is script execution.
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

/**
 * Static headers for next.config.js.
 *
 * NOTE (#936): no Content-Security-Policy here. HTML documents get their CSP
 * from proxy.ts, which mints a per-request nonce; a static CSP cannot carry one
 * and would have to keep 'unsafe-inline'. Two CSP headers on one response are
 * intersected by the browser, so leaving the static one in place would have
 * re-imposed the weaker policy's absence of a nonce and blocked every script.
 */
function securityHeaders(env = process.env) {
  return [
    { key: 'X-Content-Type-Options', value: 'nosniff' },
    { key: 'X-Frame-Options', value: 'DENY' },
    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  ];
}

module.exports = { buildCsp, buildConnectSrc, buildScriptSrc, securityHeaders };
