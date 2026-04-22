import { getStoryContext, type TestRunnerConfig } from "@storybook/test-runner";
import AxeBuilder from "@axe-core/playwright";

import { AXE_WCAG_TAGS } from "../src/lib/a11y-config.ts";

/**
 * Story 1.6 AC2: @storybook/test-runner CI gate.
 *
 * The `postVisit` hook runs after each story finishes rendering and
 * re-executes axe-core against the page via @axe-core/playwright's
 * AxeBuilder. Violations throw → Jest-compatible failure → non-zero
 * exit → CI job fails.
 *
 * This is a *separate* axe invocation from the Storybook addon-a11y
 * panel (which runs in the dev UI only). Both read the same WCAG tag
 * list from src/lib/a11y-config.ts — one source of truth.
 *
 * Per-story opt-out is honored via `parameters: { a11y: { disable:
 * true } }`, but only with the appeal process in docs/a11y-gates.md §7.
 *
 * NOTE: using `postVisit` (NOT the deprecated `postRender`) per the
 * Storybook 10.x test-runner API. See Dev Notes §Storybook test-runner.
 */
const config: TestRunnerConfig = {
  async postVisit(page, context) {
    const storyContext = await getStoryContext(page, context);

    // Respect explicit per-story opt-out (appeal-process governed).
    const a11yParams = storyContext.parameters?.a11y as { disable?: boolean } | undefined;
    if (a11yParams?.disable === true) return;

    const results = await new AxeBuilder({ page }).withTags([...AXE_WCAG_TAGS]).analyze();

    if (results.violations.length > 0) {
      const formatted = results.violations
        .map(
          (v) =>
            `  - ${v.id} (${v.impact ?? "unknown"}): ${v.description}\n` +
            `    nodes affected: ${v.nodes.length}\n` +
            `    help: ${v.helpUrl}`,
        )
        .join("\n");
      throw new Error(
        `Storybook a11y violations in story "${context.title} / ${context.name}":\n${formatted}`,
      );
    }
  },
};

export default config;
