import type { NextConfig } from "next";

const backendOrigin =
  process.env.BACKEND_ORIGIN?.replace(/\/$/, "") ??
  "http://127.0.0.1:8001";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      // The FastAPI query route is declared as POST /query/ and otherwise
      // redirects /query -> /query/. When that redirect crosses from the
      // frontend proxy to the backend origin, the browser performs a CORS
      // preflight. Proxy directly to the canonical backend route instead.
      {
        source: "/api/backend/query",
        destination: `${backendOrigin}/query/`,
      },
      {
        source: "/api/backend/:path*",
        destination: `${backendOrigin}/:path*`,
      },
    ];
  },
};

export default nextConfig;