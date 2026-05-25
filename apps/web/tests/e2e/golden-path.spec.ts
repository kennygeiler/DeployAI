import { expect, test } from "@playwright/test";

/**
 * Phase D D1.d: golden-path smoke. Walks the strategist surfaces a real
 * user lands on in the first minute — root redirect, the settings hub,
 * audit log, and the email paste-import form. Read-only — create/mutate
 * flows need DB seed and ride a heavier slice.
 *
 * Headers (`x-deployai-role` + `x-deployai-tenant`) mirror the dev-role
 * injection middleware enables under `next dev` or
 * `DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1`; the production `next start` this
 * config boots needs them set explicitly.
 */
test.describe("golden path", () => {
  test.use({
    extraHTTPHeaders: {
      "x-deployai-role": "deployment_strategist",
      "x-deployai-tenant": "11111111-1111-1111-1111-111111111111",
    },
  });

  test("root either lands on engagements or redirects to onboarding when tenant is empty", async ({
    page,
  }) => {
    const response = await page.goto("/");
    expect(response?.status(), "root responds 200").toBe(200);
    await expect(page.locator("main")).toBeVisible();
    expect(page.url()).toMatch(/\/(engagements|onboarding)(?:\/|\?|$)/);
  });

  test("settings hub renders the Settings heading", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.locator("main")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Settings", level: 1 })).toBeVisible();
  });

  test("audit log page loads (rows may be empty)", async ({ page }) => {
    await page.goto("/settings/audit");
    await expect(page.locator("main")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Audit log", level: 1 })).toBeVisible();
    // Either the table or the friendly empty-state copy must resolve once
    // the client fetch settles. Either is a green signal — the page
    // mounted, fetched, and rendered something coherent.
    await expect(
      page.locator("table").or(page.getByText("No activity events match these filters.")),
    ).toBeVisible();
  });

  test("email paste-import form is visible", async ({ page }) => {
    await page.goto("/settings/email-import");
    await expect(page.locator("main")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Email paste-import", level: 1 })).toBeVisible();
    // The paste form is the whole reason this page exists.
    await expect(page.locator("form")).toBeVisible();
  });
});
