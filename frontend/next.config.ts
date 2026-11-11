import path from "node:path";
import type { NextConfig } from "next";

// Raíz del monorepo: el frontend importa `../design/generated` y `../contracts`.
const repoRoot = path.resolve(import.meta.dirname, "..");

// Origen de la API Django. El navegador solo habla con el origen del frontend:
// las cookies quedan en este origen y no hace falta CORS.
const apiOrigin = process.env.API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Sin AGENTS.md generado por `next dev`.
  agentRules: false,
  outputFileTracingRoot: repoRoot,
  turbopack: {
    root: repoRoot,
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiOrigin}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
