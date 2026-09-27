/**
 * Backend rewrites must refuse a request that already carries client-address
 * headers (#1274).
 *
 * Next's proxy fills in X-Forwarded-For only when it is absent (`??=`), so a
 * client-sent `X-Forwarded-For: 127.0.0.1` used to reach the backend verbatim
 * from a loopback peer — exactly what the /auth/register bootstrap gate and the
 * rate limiter read as "this host". The rewrite now does not match such a
 * request (a 404), so everything it does forward carries the real peer address.
 *
 * Evaluated with Next's own `matchHas`, the function its router runs on
 * `has`/`missing`, rather than re-implementing the semantics here.
 */
import nextConfig from '../../next.config';
import { matchHas } from 'next/dist/shared/lib/router/utils/prepare-destination';

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
