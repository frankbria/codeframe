/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Use environment variable for backend URL, fallback to dev port 8080
    const backendPort = process.env.BACKEND_PORT || '8080';
    const backendUrl = `http://localhost:${backendPort}`;

    return {
      beforeFiles: [
        // WebSocket endpoint - must be proxied to FastAPI
        {
          source: '/ws',
          destination: `${backendUrl}/ws`,
        },
        // Proxy non-auth API routes to FastAPI backend
        // IMPORTANT: BetterAuth routes (/api/auth/*) are handled by Next.js
        // and must NOT be proxied to the backend
        {
          source: '/api/((?!auth).*)', // Match /api/* except /api/auth/*
          destination: `${backendUrl}/api/:path*`, // Proxy to FastAPI
        },
      ],
    };
  },
};

module.exports = nextConfig;
