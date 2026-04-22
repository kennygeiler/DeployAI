import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.{test,spec}.ts"],
    globals: false,
    // Do NOT set passWithNoTests — this package exists to house token tests.
    // A missing test file means something broke in the discovery, not "no tests".
  },
});
