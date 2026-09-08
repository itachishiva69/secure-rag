import type { NextConfig } from "next";

const backendOrigin =
  process.env.BACKEND_ORIGIN?.replace(/\/$/, "") ??
  "http://127.0.0.1:8001";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/backend/query",
        destination: `${backendOrigin}/query/`,
      },
      {
        source: "/api/backend/departments",
        destination: `${backendOrigin}/departments/`,
      },
      {
        source: "/api/backend/users",
        destination: `${backendOrigin}/users/`,
      },
      {
        source: "/api/backend/conversations",
        destination: `${backendOrigin}/conversations/`,
      },
      {
        source: "/api/backend/:path*",
        destination: `${backendOrigin}/:path*`,
      },
    ];
  },
};

export default nextConfig;