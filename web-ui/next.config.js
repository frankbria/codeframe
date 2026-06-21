const { securityHeaders } = require('./security-headers');

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Defense-in-depth CSP + hardening headers (#657): contains any future XSS
  // so an injected script can't exfiltrate the localStorage JWT.
  async headers() {
    return [{ source: '/:path*', headers: securityHeaders() }];
  },
  async rewrites() {
    return {
      beforeFiles: [
        {
          source: '/api/:path*',
          destination: 'http://localhost:8000/api/:path*',
        },
        // Auth endpoints (/auth/jwt/login, /auth/register) live outside the
        // /api prefix on the FastAPI server; proxy them too so the login flow
        // works with the default empty NEXT_PUBLIC_API_URL (#336).
        {
          source: '/auth/:path*',
          destination: 'http://localhost:8000/auth/:path*',
        },
      ],
    };
  },
};

module.exports = nextConfig;
