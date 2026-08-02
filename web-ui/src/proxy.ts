/**
 * Per-request CSP nonce (#936).
 *
 * The production CSP used to ship `script-src 'self' 'unsafe-inline'`, and the
 * security-headers comment conceded the consequence: with the JWT in
 * localStorage and inline scripts allowed, any future HTML-injection bug became
 * full session theft. connect-src/img-src closed fetch/XHR/img exfiltration, but
 * nothing could close top-level navigation (`window.location = attacker + token`)
 * once the injected script was already running.
 *
 * A nonce fixes the actual problem rather than the exfil channels: an injected
 * inline script has no nonce, so it never executes.
 *
 * This must be a proxy (not a static `headers()` entry) because the nonce has to
 * differ per request — a constant nonce is worth exactly as much as
 * 'unsafe-inline'.
 */
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

// security-headers.js is CommonJS (next.config.js requires it); the bundler
// handles the interop. ESM here because the lint gate forbids require().
import { buildCsp } from '../security-headers';

export function proxy(request: NextRequest) {
  // crypto.getRandomValues: available on the Edge runtime, unlike node:crypto.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  const nonce = btoa(String.fromCharCode(...bytes));

  const csp = buildCsp(process.env, { nonce });

  // Set on the REQUEST headers too: Next.js reads the nonce from the CSP header
  // it receives and stamps it onto the framework's own inline bootstrap scripts.
  // Without this the page's own scripts would be blocked by the policy we just
  // set — the failure mode is a blank page, so it is not subtle.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-nonce', nonce);
  requestHeaders.set('Content-Security-Policy', csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set('Content-Security-Policy', csp);
  return response;
}

export const config = {
  matcher: [
    {
      // Everything except API routes, static assets and the favicon. Those are
      // not HTML documents, so they need no nonce; next.config.js still applies
      // the non-CSP hardening headers to them.
      source: '/((?!api|_next/static|_next/image|favicon.ico).*)',
      // Prefetches are not rendered, so nonce-ing them only costs work.
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
};
