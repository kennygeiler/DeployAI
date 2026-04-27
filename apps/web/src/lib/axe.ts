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

// Module-scoped guard against React 19 Strict Mode's double-invoke of
// `useEffect` — without this, each dev-server mount stacks another
// axe-core MutationObserver and duplicates console violations. The
// module survives Strict Mode's mount/unmount/re-mount cycle because it
// is loaded once per client session.
let initialized = false;

export async function initAxeInDev(): Promise<void> {
  if (process.env.NODE_ENV !== "development") return;
  if (typeof window === "undefined") return;
  if (initialized) return;
  initialized = true;

  try {
    const [reactMod, reactDomMod, axeMod] = await Promise.all([
      import("react"),
      import("react-dom"),
      import("@axe-core/react"),
    ]);
    const axe = axeMod.default ?? axeMod;
    // Dynamic `import("react")` yields a namespace object whose exports are getters only.
    // @axe-core/react assigns `React.createElement = …` (see upstream reactAxe); pass the
    // default export — the real React module object — or initialization throws:
    // "Cannot set property createElement of [object Module] which has only a getter".
    const React = reactMod.default;
    const ReactDOM = reactDomMod.default;
    if (React == null || ReactDOM == null) {
      throw new Error("react or react-dom missing default export");
    }
    // Use the object-form `{type: 'tag', values: [...]}` rather than a
    // bare string[]. axe-core's runtime auto-detects arrays of known
    // tags as tags (so the bare form worked), but any typo silently
    // falls through to rule-ID matching → zero rules execute → silent
    // no-op. The object form is unambiguous and self-documenting.
    await axe(React, ReactDOM, 1000, {
      runOnly: { type: "tag", values: [...AXE_WCAG_TAGS] },
      // @axe-core/react's ReactSpec types `runOnly` as `string[]`,
      // but axe-core's RunOptions also accepts the object form used
      // above. Cast through `unknown` to bypass the upstream type
      // bug without losing our config's shape.
    } as unknown as Parameters<typeof axe>[3]);
  } catch (error) {
    initialized = false;
    console.warn("[a11y] @axe-core/react failed to initialize:", error);
  }
}
