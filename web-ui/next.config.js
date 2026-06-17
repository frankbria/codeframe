/** @type {import('next').NextConfig} */
const nextConfig = {
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
