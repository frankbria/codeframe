const { securityHeaders } = require('./security-headers');

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Standalone output: the Docker runner ships server.js plus only the
  // node_modules it needs, instead of the whole tree (#1121). Additive —
  // `npm run build` / `npm start` are unchanged for local dev.
  output: 'standalone',
  // Defense-in-depth CSP + hardening headers (#657): contains any future XSS
  // so an injected script can't exfiltrate the localStorage JWT.
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders() }];
  },
  async rewrites() {
    // BACKEND_ORIGIN is a BUILD-TIME env, not a runtime one. Standalone output
    // snapshots this config into .next/required-server-files.json during
    // `next build`, so setting it on the container has no effect — verified by
    // watching the container still dial localhost:8000 (#1121). It is a
    // build arg in web-ui/Dockerfile alongside NEXT_PUBLIC_*, for the same
    // reason and with the same consequence: one image per environment.
    // Default unchanged for local dev.
    const backendOrigin = process.env.BACKEND_ORIGIN || 'http://localhost:8000';
    return {
      beforeFiles: [
        {
          source: '/api/:path*',
          destination: `${backendOrigin}/api/:path*`,
        },
        // Auth endpoints (/auth/jwt/login, /auth/register) live outside the
        // /api prefix on the FastAPI server; proxy them too so the login flow
        // works with the default empty NEXT_PUBLIC_API_URL (#336).
        {
          source: '/auth/:path*',
          destination: `${backendOrigin}/auth/:path*`,
        },
      ],
    };
  },
};

module.exports = nextConfig;
