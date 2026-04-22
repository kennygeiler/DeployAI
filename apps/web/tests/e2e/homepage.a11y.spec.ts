import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { AXE_WCAG_TAGS } from "../../src/lib/a11y-config";

/**
 * Story 1.6 AC4: homepage a11y baseline. Landmark + zero-violation +
 * keyboard-smoke checks on `/`. The WCAG tag list is imported from the
 * shared a11y-config module so this spec, Storybook's test-runner, and
 * @axe-core/react all agree on "which WCAG floors we're gating on".
 */
test.describe("homepage a11y baseline", () => {
  test("returns 200 and renders a <main> landmark", async ({ page }) => {
    const response = await page.goto("/");
    expect(response?.status(), "homepage returns 200").toBe(200);
    await expect(page.locator("main")).toBeVisible();
  });

  test("has zero axe violations at WCAG 2.0/2.1/2.2 AA", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("main")).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags([...AXE_WCAG_TAGS]).analyze();

    expect(
      results.violations,
      `Unexpected a11y violations:\n${JSON.stringify(results.violations, null, 2)}`,
    ).toEqual([]);
  });

  test("first Tab lands on a focusable element, not <body>", async ({ page }) => {
    await page.goto("/");
    await expect(page.locator("main")).toBeVisible();
    await page.keyboard.press("Tab");
    const active = await page.evaluate(() => document.activeElement?.tagName ?? "BODY");
    expect(
      ["A", "BUTTON", "INPUT", "TEXTAREA", "SELECT"],
      `first Tab landed on ${active}`,
    ).toContain(active);
  });
});
