/**
 * Shared accessibility configuration — the single source of truth for
 * axe-core invocations across every a11y gate that Story 1.6 lands:
 *
 *   - Storybook addon-a11y panel            (.storybook/preview.ts)
 *   - Storybook test-runner CI gate         (.storybook/test-runner.ts)
 *   - Playwright E2E + @axe-core/playwright (tests/e2e/*.spec.ts)
 *   - @axe-core/react dev runtime           (src/lib/axe.ts)
 *
 * Keeping the WCAG tag list in one module means "we gate on WCAG 2.2 AA"
 * is a single-source-of-truth decision rather than a literal scattered
 * across five files. See docs/a11y-gates.md §Axe version alignment and
 * §WCAG tag set for the contract.
 *
 * Note: `.pa11yci.json` cannot import TypeScript; the tag coupling there
 * lives as a `_comment` field that points at docs/a11y-gates.md so any
 * drift surfaces in doc review.
 */

export const AXE_WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] as const;

/**
 * Rules intentionally disabled across every gate. Adding a rule here
 * requires an appeal per docs/a11y-gates.md §Appeal process — inline
 * rationale comment + linked tracking issue — never a silent entry.
 *
 * Intentionally empty at Story 1.6.
 */
export const AXE_DISABLED_RULES: readonly string[] = [];
