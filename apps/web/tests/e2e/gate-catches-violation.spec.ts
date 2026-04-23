import { pathToFileURL } from "node:url";
import { resolve } from "node:path";

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { AXE_WCAG_TAGS } from "../../src/lib/a11y-config";

/**
 * Story 1.6 AC10: gate-proof self-test.
 *
 * Loads a static HTML fixture with a deliberate `image-alt` violation
 * and asserts that axe-core reports ≥ 1 violation. If axe is silently
 * misconfigured (e.g., wrong tag list, wrong builder wiring), this
 * spec fails — i.e., the gate proves itself.
 *
 * NOT a PR-blocker. Guarded by `GATE_PROOF=1` so it runs only on
 * nightly schedules or manual invocations:
 *
 *   GATE_PROOF=1 pnpm --filter @deployai/web test:e2e \
 *     tests/e2e/gate-catches-violation.spec.ts
 *
 * The homepage baseline (homepage.a11y.spec.ts) is the PR-blocking
 * gate; this spec validates that the gate's machinery actually fires.
 */
test.describe("gate-proof: axe catches a known violation", () => {
  test.skip(
    process.env.GATE_PROOF !== "1",
    "Gate-proof spec — set GATE_PROOF=1 to run (nightly / on demand only).",
  );

  test("image-alt violation on static fixture surfaces via AxeBuilder", async ({ page }) => {
    const fixture = pathToFileURL(resolve(__dirname, "fixtures", "violating-page.html")).toString();
    await page.goto(fixture);

    // Exercise the *same* tag pipeline production specs use — if the
    // shared config is silently corrupted (e.g., a typo turns a tag
    // into a rule ID and matches nothing), this self-test must fail
    // too. Otherwise the gate-proof is a false alarm generator.
    const results = await new AxeBuilder({ page }).withTags([...AXE_WCAG_TAGS]).analyze();
    const imageAltViolation = results.violations.find((v) => v.id === "image-alt");

    expect(
      imageAltViolation,
      "axe failed to surface the intentional `image-alt` violation — " +
        "the gate is silently misconfigured.",
    ).toBeDefined();
  });
});
