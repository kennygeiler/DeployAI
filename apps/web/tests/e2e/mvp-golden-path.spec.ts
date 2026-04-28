import { expect, test } from "@playwright/test";

const strategistRoleHeader = { "x-deployai-role": "deployment_strategist" };

/**
 * MVP operating plan — Track E: E2E smoke on the golden path
 * (strategist dev session → digest → one evidence view with trust surface).
 *
 * Uses the same stable interactions as Story 8.4 (`strategist-command-palette.spec.ts`):
 * expand digest citation → “Navigate to source” → `/evidence/:nodeId` + `EvidencePanel`.
 * Cmd+K BFF-typed search is covered by unit + integration tests; cmdk+Playwright for that path
 * remains finicky in CI — follow up in Track E if we need an additional palette-only spec.
 */
test.describe("MVP Track E — golden path", () => {
  test.use({ extraHTTPHeaders: strategistRoleHeader });
  test.describe.configure({ mode: "serial" });

  test("digest → inline citation → /evidence/:nodeId (trust loop)", async ({ page }) => {
    const id = "2d4437ee-9336-441e-ab57-121b81ee57a4";
    await page.goto("/digest", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /Morning digest/i })).toBeVisible();
    const chip = page.locator("[data-citation-chip]").first();
    await expect(chip).toBeVisible({ timeout: 15_000 });
    await chip.click();
    const deepLink = page.locator(`a[href="/evidence/${id}"]`);
    await expect(deepLink).toBeVisible({ timeout: 15_000 });
    await page.evaluate((href) => {
      document.querySelector<HTMLAnchorElement>(`a[href="${href}"]`)?.click();
    }, `/evidence/${id}`);
    await expect(page).toHaveURL(new RegExp(`/evidence/${id}`));
    await expect(page.getByRole("heading", { name: /Evidence node/i })).toBeVisible();
    await expect(page.locator("[data-evidence-panel]")).toBeVisible();
  });
});
