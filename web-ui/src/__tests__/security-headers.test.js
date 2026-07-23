/**
 * Security headers / CSP builder tests (#657).
 *
 * The CSP's exfil-containment value lives in connect-src / img-src /
 * object-src / base-uri / frame-ancestors — these tests pin that lockdown so a
 * future edit can't silently widen it (e.g. to `connect-src *`).
 */
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

  test('securityHeaders ships the CSP plus the hardening header set', () => {
    const keys = securityHeaders({}).map((h) => h.key);
    expect(keys).toEqual(
      expect.arrayContaining([
        'Content-Security-Policy',
        'X-Content-Type-Options',
        'X-Frame-Options',
        'Referrer-Policy',
      ])
    );
  });
});
