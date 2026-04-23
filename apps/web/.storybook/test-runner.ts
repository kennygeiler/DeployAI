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
type A11yOverride = { disable?: boolean; reason?: string };

const config: TestRunnerConfig = {
  async postVisit(page, context) {
    const storyContext = await getStoryContext(page, context);

    // Per-story opt-out (appeal-process governed, docs/a11y-gates.md §7).
    //
    // `storyContext.parameters` is merged (global → meta → story). A
    // bare `disable: true` at the preview.ts level would silently
    // disable EVERY story and the CI gate would stay green auditing
    // zero stories. Two mitigations:
    //
    //   (a) require a `reason` string alongside `disable: true` — a
    //       one-line rationale that points at the tracking issue per
    //       the appeal process. Accidental global disables rarely ship
    //       with a reason field.
    //   (b) log the skip so the CI log reviewer sees it.
    //
    // If (a) is violated (disable without reason), throw so the gate
    // fails loudly rather than silently skipping.
    const a11yParams = storyContext.parameters?.a11y as A11yOverride | undefined;
    if (a11yParams?.disable === true) {
      if (!a11yParams.reason) {
        throw new Error(
          `[a11y] Story "${context.title} / ${context.name}" has ` +
            `parameters.a11y.disable=true without a required \`reason\` ` +
            `string. See docs/a11y-gates.md §Appeal process.`,
        );
      }
      console.warn(
        `[a11y] axe skipped for "${context.title} / ${context.name}" ` +
          `(appeal: ${a11yParams.reason})`,
      );
      return;
    }

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
