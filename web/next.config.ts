import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // @arcana/schema ships TypeScript source; Next must transpile it.
  transpilePackages: ["@arcana/schema"],
};

export default nextConfig;
