import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone", // minimal production server: .next/standalone/apps/web/server.js
  // The pnpm workspace root; pinned so the standalone layout never depends on stray lockfiles.
  outputFileTracingRoot: path.join(__dirname, "../.."),
  turbopack: { root: path.join(__dirname, "../..") },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
