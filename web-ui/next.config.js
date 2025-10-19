/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    // Use environment variable for backend URL, fallback to dev port 8080
    const backendPort = process.env.BACKEND_PORT || '8080';
    const backendUrl = `http://localhost:${backendPort}`;

    return [
      {
        source: '/api/:path*',
        destination: `${backendUrl}/api/:path*`, // Proxy to FastAPI
      },
      {
        source: '/ws',
        destination: `${backendUrl}/ws`,
      },
    ];
  },
};

module.exports = nextConfig;
