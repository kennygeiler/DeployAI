import { expect, test } from "@playwright/test";

const strategistRoleHeader = { "x-deployai-role": "deployment_strategist" };

/**
 * All strategist browser tests run serially: parallel navigations + one `next start` process
 * were observed to produce `net::ERR_ABORTED` under load.
 *
 * Note: `pnpm start` logs a warning with `output: "standalone"`; client `router.push` from cmdk
 * can make Playwright pointer/Enter actions block until timeout. We still validate open/close and
 * full-page loads; use direct `page.goto` where palette-driven navigation is unreliable in CI.
 */
test.describe("strategist", () => {
  test.describe.configure({ mode: "serial" });

  test.describe("strategist command palette (Epic 8.6)", () => {
    test.use({ extraHTTPHeaders: strategistRoleHeader });

    test("open palette (⌃K) and close on phase-tracking and digest", async ({ page }) => {
      await page.goto("/phase-tracking", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: /Phase & task tracking/i })).toBeVisible();
      await page.keyboard.press("Control+K");
      await expect(page.getByRole("dialog")).toBeVisible();
      await expect(page.getByTestId("command-palette-input")).toBeVisible();
      // Playwright's synthesized click/keyboard often stalls at "performing action" in this
      // Radix+cmdk+next stack; DOM click returns immediately in CI.
      await page.evaluate(() => {
        document.querySelector<HTMLButtonElement>("[data-slot=dialog-close]")?.click();
      });
      await expect(page.getByRole("dialog")).not.toBeVisible();

      await page.goto("/digest", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: /Morning digest/i })).toBeVisible();
      await page.keyboard.press("Control+K");
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.evaluate(() => {
        document.querySelector<HTMLButtonElement>("[data-slot=dialog-close]")?.click();
      });
      await expect(page.getByRole("dialog")).not.toBeVisible();
    });

    test("arrow keys cross Navigate group and CommandSeparator (first Action item)", async ({
      page,
    }) => {
      await page.goto("/digest", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: /Morning digest/i })).toBeVisible();
      await page.keyboard.press("Control+K");
      await expect(page.getByRole("dialog")).toBeVisible();
      const input = page.getByTestId("command-palette-input");
      await expect(input).toBeVisible();
      // Roving: 4 Navigate items, then the Actions group (CommandSeparator is not a focus stop).
      // Four ArrowDown moves from the input land on the first Action row in this build.
      for (let i = 0; i < 4; i += 1) {
        await page.keyboard.press("ArrowDown");
      }
      await expect(page.locator('[cmdk-item][aria-selected="true"]')).toContainText(
        /Resolve|claim|Action Queue/i,
      );
      await page.evaluate(() => {
        document.querySelector<HTMLButtonElement>("[data-slot=dialog-close]")?.click();
      });
    });
  });

  test.describe("strategist activity BFF (control plane + ingestion)", () => {
    test.use({ extraHTTPHeaders: strategistRoleHeader });

    const isoToday = () => new Date().toISOString().slice(0, 10);

    test("ingestion in progress shows top-rail status", async ({ page }) => {
      await page.route("**/api/internal/strategist-activity*", async (route) => {
        if (route.request().method() !== "GET") {
          await route.continue();
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            agentDegraded: false,
            ingestionInProgress: true,
            controlPlane: "ok",
            strategistLocalDate: isoToday(),
          }),
        });
      });
      await page.goto("/digest", { waitUntil: "domcontentloaded" });
      await expect(page.locator("[data-ingestion-active]")).toBeVisible({ timeout: 20_000 });
    });

    test("agent degraded shows Oracle outage (role=alert)", async ({ page }) => {
      await page.route("**/api/internal/strategist-activity*", async (route) => {
        if (route.request().method() !== "GET") {
          await route.continue();
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            agentDegraded: true,
            ingestionInProgress: false,
            controlPlane: "error",
            strategistLocalDate: isoToday(),
          }),
        });
      });
      await page.goto("/digest", { waitUntil: "domcontentloaded" });
      const outage = page.locator("[data-agent-outage]");
      await expect(outage).toBeVisible({ timeout: 20_000 });
      await expect(outage).toContainText("Oracle");
    });
  });

  test.describe("Story 8.7 — agent + ingestion on all three surfaces (mock BFF)", () => {
    test.use({ extraHTTPHeaders: strategistRoleHeader });

    const today = () => new Date().toISOString().slice(0, 10);

    for (const [path, heading] of [
      ["/evening", /Evening synthesis/i] as const,
      ["/phase-tracking", /Phase & task tracking/i] as const,
    ] as const) {
      test(`ingestion top-rail on ${path}`, async ({ page }) => {
        await page.route("**/api/internal/strategist-activity*", async (route) => {
          if (route.request().method() !== "GET") {
            await route.continue();
            return;
          }
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              agentDegraded: false,
              ingestionInProgress: true,
              controlPlane: "ok",
              strategistLocalDate: today(),
            }),
          });
        });
        await page.goto(path, { waitUntil: "domcontentloaded" });
        await expect(page.getByRole("heading", { name: heading })).toBeVisible();
        await expect(page.locator("[data-ingestion-active]")).toBeVisible({ timeout: 20_000 });
      });

      test(`agent outage banner on ${path}`, async ({ page }) => {
        await page.route("**/api/internal/strategist-activity*", async (route) => {
          if (route.request().method() !== "GET") {
            await route.continue();
            return;
          }
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              agentDegraded: true,
              ingestionInProgress: false,
              controlPlane: "error",
              strategistLocalDate: today(),
            }),
          });
        });
        await page.goto(path, { waitUntil: "domcontentloaded" });
        await expect(page.getByRole("heading", { name: heading })).toBeVisible();
        const outage = page.locator("[data-agent-outage]");
        await expect(outage).toBeVisible({ timeout: 20_000 });
        await expect(outage).toContainText("Oracle");
      });
    }
  });

  test.describe("Story 8.4 — expand-inline EvidencePanel (NFR4 budget in CI)", () => {
    test.use({ extraHTTPHeaders: strategistRoleHeader });

    test("citation chip shows [data-evidence-panel] under 2s (NFR4 slack in CI)", async ({
      page,
    }) => {
      await page.goto("/digest", { waitUntil: "domcontentloaded" });
      const chip = page.locator("[data-citation-chip]").first();
      await expect(chip).toBeVisible();
      const t0 = Date.now();
      // Same Playwright+Radix quirk as cmdk: use DOM click, not locator.click, for stable CI.
      await page.evaluate(() => {
        (document.querySelector("[data-citation-chip]") as HTMLButtonElement | null)?.click();
      });
      const panel = page.locator("[data-evidence-panel]");
      await expect(panel).toBeVisible();
      const ms = Date.now() - t0;
      expect(ms, `NFR4 expand-inline: panel visible in <2000ms (was ${ms}ms)`).toBeLessThan(2000);
    });
  });

  test.describe("strategist route middleware", () => {
    test("returns 403 for /digest when x-deployai-role is missing", async ({ page }) => {
      const r = await page.goto("/digest", { waitUntil: "domcontentloaded" });
      expect(r?.status(), "unauthenticated /digest should be forbidden at edge").toBe(403);
    });
  });

  test.describe("Story 8.4 — /evidence/:nodeId", () => {
    test.use({ extraHTTPHeaders: strategistRoleHeader });

    test("renders breadcrumb and evidence for a digest node id", async ({ page }) => {
      const id = "2d4437ee-9336-441e-ab57-121b81ee57a4";
      await page.goto(`/evidence/${encodeURIComponent(id)}`, { waitUntil: "domcontentloaded" });
      await expect(page.getByTestId("evidence-breadcrumb")).toBeVisible();
      await expect(page.getByRole("heading", { name: /Evidence node/i })).toBeVisible();
      await expect(page.locator("[data-evidence-panel]")).toBeVisible();
    });

    test("placeholder strategist routes return 200", async ({ page }) => {
      for (const path of [
        "/validation-queue",
        "/solidification-review",
        "/overrides",
        "/audit/personal",
      ]) {
        const r = await page.goto(path, { waitUntil: "domcontentloaded" });
        expect(r?.status(), path).toBe(200);
      }
    });
  });
});
