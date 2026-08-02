/**
 * Security headers / CSP builder tests (#657).
 *
 * The CSP's exfil-containment value lives in connect-src / img-src /
 * object-src / base-uri / frame-ancestors — these tests pin that lockdown so a
 * future edit can't silently widen it (e.g. to `connect-src *`).
 */
import fs from 'fs';
import path from 'path';

import { buildCsp, buildConnectSrc, securityHeaders } from '../../security-headers';

describe('security headers (#657)', () => {
  test('CSP locks down the exfil-relevant directives', () => {
    const csp = buildCsp({});
    expect(csp).toContain("default-src 'self'");
    expect(csp).toContain("object-src 'none'");
    expect(csp).toContain("base-uri 'self'");
    expect(csp).toContain("frame-ancestors 'none'");
    // The GitHub owner avatar is the only allowed external image host;
    // anything else would re-open a GET-based exfil channel.
    expect(csp).toContain('https://avatars.githubusercontent.com');
    expect(csp).not.toContain('img-src *');
  });

  test('connect-src includes self and the configured backend + ws origins', () => {
    const cs = buildConnectSrc({
      apiUrl: 'https://api.example.com',
      wsUrl: 'wss://api.example.com',
    });
    expect(cs).toContain("'self'");
    expect(cs).toContain('https://api.example.com');
    expect(cs).toContain('wss://api.example.com');
  });

  test('connect-src never falls back to a wildcard', () => {
    // Empty env (same-origin API, default ws) must still be a closed list.
    const cs = buildConnectSrc({ apiUrl: '', wsUrl: '' });
    expect(cs).not.toContain('*');
    expect(cs).toContain("'self'");
    expect(cs).toContain('ws://localhost:8000');
  });

  test('production CSP does not allow eval (#783)', () => {
    // unsafe-eval is only needed by the Next.js dev runtime (React Refresh);
    // shipping it in production widens the XSS surface for no benefit.
    expect(buildCsp({})).not.toContain("'unsafe-eval'");
    expect(buildCsp({ NODE_ENV: 'production' })).not.toContain("'unsafe-eval'");
  });

  test('dev CSP allows eval for the Next.js dev runtime', () => {
    expect(buildCsp({ NODE_ENV: 'development' })).toContain("'unsafe-eval'");
  });

  test('securityHeaders ships the hardening header set', () => {
    // The CSP moved OUT of this static set in #936: HTML documents get it from
    // proxy.ts, which mints a per-request nonce. A static CSP cannot carry one,
    // and two CSP headers on a response are intersected — so leaving it here
    // would have blocked every script. Asserted explicitly below.
    const keys = securityHeaders({}).map((h) => h.key);
    expect(keys).toEqual(
      expect.arrayContaining([
        'X-Content-Type-Options',
        'X-Frame-Options',
        'Referrer-Policy',
      ])
    );
  });
});

describe('production CSP carries a nonce, not unsafe-inline (#936)', () => {
  const PROD = { NODE_ENV: 'production' };

  /** The AC's CI check: the production policy must not allow inline script. */
  test('script-src has no unsafe-inline in production', () => {
    const scriptSrc = buildCsp(PROD, { nonce: 'test-nonce' })
      .split('; ')
      .find((d) => d.startsWith('script-src'));

    expect(scriptSrc).toBeDefined();
    expect(scriptSrc).not.toContain("'unsafe-inline'");
  });

  test('script-src carries the request nonce and strict-dynamic', () => {
    const scriptSrc = buildCsp(PROD, { nonce: 'abc123' })
      .split('; ')
      .find((d) => d.startsWith('script-src'));

    expect(scriptSrc).toContain("'nonce-abc123'");
    expect(scriptSrc).toContain("'strict-dynamic'");
  });

  test('production never ships unsafe-eval', () => {
    expect(buildCsp(PROD, { nonce: 'n' })).not.toContain("'unsafe-eval'");
  });

  test('development keeps unsafe-eval for the Next.js dev runtime', () => {
    const csp = buildCsp({ NODE_ENV: 'development' }, { nonce: 'n' });
    expect(csp).toContain("'unsafe-eval'");
    // ...but still no unsafe-inline: the nonce works in dev too.
    const scriptSrc = csp.split('; ').find((d) => d.startsWith('script-src'));
    expect(scriptSrc).not.toContain("'unsafe-inline'");
  });

  test('style-src deliberately keeps unsafe-inline', () => {
    // Documented decision: Tailwind/React set style attributes directly, and a
    // stolen style is not a stolen session. If this ever changes it should be a
    // conscious edit, not a silent one.
    const styleSrc = buildCsp(PROD, { nonce: 'n' })
      .split('; ')
      .find((d) => d.startsWith('style-src'));
    expect(styleSrc).toContain("'unsafe-inline'");
  });

  test('the static header set no longer carries a CSP', () => {
    // Two CSP headers are intersected by the browser, so a static (nonce-less)
    // one alongside the proxy's would block every script.
    const keys = securityHeaders(PROD).map((h) => h.key);
    expect(keys).not.toContain('Content-Security-Policy');
    expect(keys).toContain('X-Content-Type-Options');
  });

  test('a missing nonce still produces a working policy', () => {
    // Non-document responses fall back to this; it must not be empty or broken.
    const scriptSrc = buildCsp(PROD)
      .split('; ')
      .find((d) => d.startsWith('script-src'));
    expect(scriptSrc).toContain("'self'");
  });
});

describe('the nonce requires dynamic rendering (#936)', () => {
  test('the root layout forces dynamic rendering', () => {
    // Next.js can only stamp a per-request nonce onto a document it renders at
    // request time. Measured on a statically prerendered route: 0 of 21 scripts
    // carried the nonce — with 'strict-dynamic' and no 'unsafe-inline' that is a
    // blank page. Deleting this export would reintroduce that silently, since
    // the build still succeeds.
    const layout = fs.readFileSync(
      path.join(__dirname, '..', 'app', 'layout.tsx'),
      'utf8'
    );
    expect(layout).toMatch(/export const dynamic = 'force-dynamic'/);
  });

  test('proxy.ts sets the CSP on both request and response headers', () => {
    const proxy = fs.readFileSync(path.join(__dirname, '..', 'proxy.ts'), 'utf8');
    // The REQUEST header is what Next.js reads to nonce its own scripts; the
    // RESPONSE header is what the browser enforces. Both are required — with
    // only the response header set, the policy blocks the page's own scripts.
    expect(proxy).toMatch(/requestHeaders\.set\(\s*'Content-Security-Policy'/);
    expect(proxy).toMatch(/response\.headers\.set\(\s*'Content-Security-Policy'/);
    expect(proxy).toContain('getRandomValues');
  });
});
