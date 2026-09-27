/**
 * Backend rewrites must refuse a request that already carries client-address
 * headers (#1274).
 *
 * Next's rewrite proxy keeps a client-sent `X-Forwarded-For` as is, and the
 * backend trusts loopback as a proxy, so a client could pick its own rate-limit
 * bucket. (The /auth/register gate does not rely on this — it refuses every
 * proxied request.)
 *
 * Evaluated with Next's own `matchHas`, the function its router runs on
 * `has`/`missing`, rather than re-implementing the semantics here.
 */
import nextConfig from '../../next.config';
import { matchHas } from 'next/dist/shared/lib/router/utils/prepare-destination';
import { config } from '../proxy';

const CLIENT_ADDRESS_HEADERS = ['x-forwarded-for', 'x-real-ip', 'forwarded'];

async function backendRewrites() {
  const { beforeFiles } = await nextConfig.rewrites();
  return beforeFiles.filter((r) => r.source === '/api/:path*' || r.source === '/auth/:path*');
}

function matches(rewrite, headers) {
  return Boolean(matchHas({ headers }, {}, rewrite.has || [], rewrite.missing || []));
}

describe('backend rewrites refuse client-address headers (#1274)', () => {
  test('both backend rewrites are covered', async () => {
    const sources = (await backendRewrites()).map((r) => r.source).sort();
    expect(sources).toEqual(['/api/:path*', '/auth/:path*']);
  });

  test('a plain browser request is still proxied', async () => {
    for (const rewrite of await backendRewrites()) {
      expect(matches(rewrite, { host: 'localhost:3000' })).toBe(true);
    }
  });

  test.each(CLIENT_ADDRESS_HEADERS)('a request carrying %s is not proxied', async (header) => {
    for (const rewrite of await backendRewrites()) {
      expect(matches(rewrite, { host: 'localhost:3000', [header]: '127.0.0.1' })).toBe(false);
    }
  });
});

// Only the static matcher config is under test; next/server needs a global
// Request that jsdom lacks.
jest.mock('next/server', () => ({ NextResponse: {} }));

describe('the CSP proxy stays off backend routes (#1274)', () => {
  // Running proxy.ts adds x-forwarded-* to the request, which the rewrites
  // above then refuse — so if the proxy matched /auth, every login would 404.
  // Found by the live demo; matchHas alone cannot see it.
  test.each(['/auth/jwt/login', '/auth/register', '/api/v2/tasks'])('%s is not matched', (path) => {
    const source = config.matcher[0].source;
    expect(new RegExp(`^${source}$`).test(path)).toBe(false);
  });

  test('pages are still matched', () => {
    const source = config.matcher[0].source;
    expect(new RegExp(`^${source}$`).test('/login')).toBe(true);
    expect(new RegExp(`^${source}$`).test('/tasks')).toBe(true);
  });
});
