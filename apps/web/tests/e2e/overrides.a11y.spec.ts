import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { AXE_WCAG_TAGS } from "../../src/lib/a11y-config";

const strategistRoleHeader = { "x-deployai-role": "deployment_strategist" as const };

/** Epic 10.6 — axe-playwright gate on /overrides (TanStack table + composer). */
test.describe("overrides surface a11y", () => {
  test.use({ extraHTTPHeaders: strategistRoleHeader });

  test("loads override history and passes axe at WCAG AA tags", async ({ page }) => {
    const response = await page.goto("/overrides", { waitUntil: "domcontentloaded" });
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { name: /Override history/i })).toBeVisible();
    const results = await new AxeBuilder({ page }).withTags([...AXE_WCAG_TAGS]).analyze();
    expect(
      results.violations,
      `Unexpected a11y violations:\n${JSON.stringify(results.violations, null, 2)}`,
    ).toEqual([]);
  });
});
