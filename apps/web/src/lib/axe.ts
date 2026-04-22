import { AXE_WCAG_TAGS } from "./a11y-config";

/**
 * Story 1.6 AC3: dev-only @axe-core/react bootstrap.
 *
 * Runs axe-core against the rendered DOM and logs violations to the
 * browser console. Only active when:
 *
 *   - `process.env.NODE_ENV === "development"` — Next.js tree-shakes
 *     this branch out of production bundles (verified at build time by
 *     grepping `.next/` for `axe-core`).
 *   - `typeof window !== "undefined"` — server-rendered paths must not
 *     load the package (SSR has no DOM to audit).
 *
 * `try/catch` is intentional: Story 1.6 Risks §1 + §2 document that
 * @axe-core/react's npm README still carries a pre-React-18
 * compatibility note and this repo uses React 19.2. If the package
 * misbehaves under React 19, we warn-and-continue rather than crash the
 * dev server. CI-side gates (Storybook test-runner, Playwright, pa11y)
 * remain the contract-enforcing layer — this is a developer-convenience
 * signal, not a PR-blocker.
 */
export async function initAxeInDev(): Promise<void> {
  if (process.env.NODE_ENV !== "development") return;
  if (typeof window === "undefined") return;

  try {
    const [React, ReactDOM, axeMod] = await Promise.all([
      import("react"),
      import("react-dom"),
      import("@axe-core/react"),
    ]);
    const axe = axeMod.default ?? axeMod;
    await axe(React, ReactDOM, 1000, {
      runOnly: [...AXE_WCAG_TAGS],
    });
  } catch (error) {
    console.warn("[a11y] @axe-core/react failed to initialize:", error);
  }
}
