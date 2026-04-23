import { defineConfig, devices } from "@playwright/test";

/**
 * Story 1.6 AC4: Playwright E2E + @axe-core/playwright.
 *
 * Scope: Chromium-desktop only at V1. See story Dev Notes §Playwright
 * scope for why (public-sector IT standardizes on Edge/Chrome, CI-time
 * minimization, a11y rules are browser-independent — cross-browser is
 * a visual-regression concern that lands post-Story-1.6).
 *
 * Server model: `webServer` boots `next start` against the production
 * build on port 3000 and waits for 200 before running tests. Locally,
 * `reuseExistingServer` attaches to any already-running `pnpm dev`
 * (10x iteration speedup); in CI, it always spawns its own for
 * determinism.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  // axe over a stable DOM is deterministic — any intermittent failure
  // is signal (hydration race, font-face timing, network flake), not
  // noise. Retries would mask it and produce green PRs that flake
  // elsewhere. Keep retries: 0 for all environments.
  retries: 0,
  workers: process.env.CI ? 1 : undefined,
  timeout: 30_000,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: "http://127.0.0.1:3000",
    trace: "on-first-retry",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  webServer: {
    command: "pnpm start",
    url: "http://127.0.0.1:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
