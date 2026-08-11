import { join } from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Pin the monorepo root explicitly — with multiple lockfiles on disk
  // (workspace checkouts, user-level lockfiles) Next.js otherwise guesses
  // the wrong workspace root and Turbopack refuses to compile.
  turbopack: {
    root: join(__dirname, "..", ".."),
  },
};

export default nextConfig;
