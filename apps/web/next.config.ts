import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export for Vercel when NEXT_OUTPUT=export (container deploys stay default)
  ...(process.env.NEXT_OUTPUT === "export" ? { output: "export" as const } : {}),
};

export default nextConfig;
