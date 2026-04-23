import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { AXE_WCAG_TAGS } from "../../src/lib/a11y-config";

const adminHeaders = { "x-deployai-role": "platform_admin" } as const;

test.describe("admin /admin/runs (Story 1.16)", () => {
  test("returns 200 with platform_admin header and has zero axe violations", async ({ page }) => {
    await page.setExtraHTTPHeaders(adminHeaders);
    const response = await page.goto("/admin/runs");
    expect(response?.status(), "/admin/runs returns 200 for platform admin").toBe(200);
    await expect(page.locator("main#main")).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags([...AXE_WCAG_TAGS]).analyze();
    expect(
      results.violations,
      `Unexpected a11y violations:\n${JSON.stringify(results.violations, null, 2)}`,
    ).toEqual([]);
  });

  test("returns 403 without dev role header", async ({ page }) => {
    const response = await page.goto("/admin/runs");
    expect(response?.status(), "missing role should get 403 from middleware").toBe(403);
  });
});
