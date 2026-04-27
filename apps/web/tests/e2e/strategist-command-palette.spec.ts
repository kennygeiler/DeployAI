import { expect, test, type Page } from "@playwright/test";

const strategistRoleHeader = { "x-deployai-role": "deployment_strategist" };

/** Bodies must satisfy `StrategistActivitySnapshot` shape for client merge. */
const meetingIdleFields = {
  inMeeting: false,
  meetingId: null,
  meetingTitle: null,
  oracleInMeetingAlertAt: null,
  meetingDetectionSource: "off",
  calendarPollIntervalSeconds: null,
} as const;

/** Client `AppShell` must be hydrated so the ⌃K listener is attached (domcontentloaded alone is not enough). */
async function waitForStrategistCommandShell(page: Page): Promise<void> {
  await expect(page.getByTestId("command-palette-trigger")).toBeVisible();
}

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
      await waitForStrategistCommandShell(page);
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
      await waitForStrategistCommandShell(page);
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
      await waitForStrategistCommandShell(page);
      await page.keyboard.press("Control+K");
      await expect(page.getByRole("dialog")).toBeVisible();
      const input = page.getByTestId("command-palette-input");
      await expect(input).toBeVisible();
      await input.click();
      // Roving crosses Navigate (6 items) and CommandSeparator (not a focus stop), then Actions.
      // cmdk minor versions differ on whether the first ArrowDown leaves the filter input — step
      // until the first Action row is selected instead of assuming a fixed key count.
      const firstActionRow = /Resolve|claim|Action Queue/i;
      let reachedAction = false;
      for (let i = 0; i < 24; i += 1) {
        await page.keyboard.press("ArrowDown");
        const selected = page.locator('[cmdk-item][aria-selected="true"]');
        await expect(selected).toBeVisible();
        if (firstActionRow.test((await selected.textContent()) ?? "")) {
          reachedAction = true;
          break;
        }
      }
      expect(reachedAction, "roving should reach the first Actions group row").toBe(true);
      await expect(page.locator('[cmdk-item][aria-selected="true"]')).toContainText(firstActionRow);
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
            agentServiceHealth: "unconfigured",
            ...meetingIdleFields,
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
            agentServiceHealth: "unconfigured",
            ...meetingIdleFields,
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
      ["/digest", /Morning digest/i] as const,
      ["/in-meeting", /In-meeting alert/i] as const,
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
              agentServiceHealth: "unconfigured",
              ...meetingIdleFields,
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
              agentServiceHealth: "unconfigured",
              ...meetingIdleFields,
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

    test("demo query ?agentError=1 shows outage without route mock (URL merge survives BFF poll)", async ({
      page,
    }) => {
      await page.goto("/digest?agentError=1", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: /Morning digest/i })).toBeVisible();
      await expect(page.locator("[data-agent-outage]")).toBeVisible({ timeout: 20_000 });
      await expect(page.getByRole("heading", { name: /What I ranked out/i })).not.toBeVisible();
    });

    test("demo query ?ingest=1 shows top-rail ingestion without route mock", async ({ page }) => {
      await page.goto("/digest?ingest=1", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: /Morning digest/i })).toBeVisible();
      await expect(page.locator("[data-ingestion-active]")).toBeVisible({ timeout: 20_000 });
    });
  });

  test.describe("Story 8.4 — expand-inline EvidencePanel (NFR4 budget in CI)", () => {
    test.use({ extraHTTPHeaders: strategistRoleHeader });

    /** NFR4: ≤1.5s p95; single CI sample uses 1500ms ceiling (same headroom class as PRD). */
    test("citation chip shows [data-evidence-panel] within 1500ms (NFR4)", async ({ page }) => {
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
      expect(ms, `NFR4 expand-inline: panel visible in ≤1500ms (was ${ms}ms)`).toBeLessThanOrEqual(
        1500,
      );
      await expect(chip).toHaveAttribute("aria-expanded", "true");
    });

    test("Navigate to source inside panel reaches /evidence/:nodeId", async ({ page }) => {
      const id = "2d4437ee-9336-441e-ab57-121b81ee57a4";
      await page.goto("/digest", { waitUntil: "domcontentloaded" });
      const chip = page.locator("[data-citation-chip]").first();
      await expect(chip).toBeVisible();
      await page.evaluate(() => {
        (document.querySelector("[data-citation-chip]") as HTMLButtonElement | null)?.click();
      });
      const panel = page.locator("[data-evidence-panel]").first();
      await expect(panel).toBeVisible();
      await expect(panel.locator("[data-evidence-panel-footer]")).toBeVisible();
      await panel.getByRole("link", { name: /navigate to source/i }).click();
      await expect(page).toHaveURL(new RegExp(`/evidence/${id}`));
      await expect(page.getByRole("heading", { name: /Evidence node/i })).toBeVisible();
    });

    test("MVP Track D — in-meeting alert reuses first digest node id in evidence link", async ({
      page,
    }) => {
      const id = "2d4437ee-9336-441e-ab57-121b81ee57a4";
      await page.goto("/in-meeting?inMeeting=1", { waitUntil: "domcontentloaded" });
      await expect(page.getByRole("heading", { name: /In-meeting alert/i })).toBeVisible();
      await expect(page.locator("[data-mvp-in-meeting-demo]")).toBeVisible();
      await expect(page.getByRole("complementary", { name: /In-meeting alert/i })).toBeVisible();
      const chip = page.locator(`#citation-in-meeting-${id}`);
      await expect(chip).toBeVisible();
      await page.evaluate((cid) => {
        (
          document.querySelector(`#citation-in-meeting-${cid}`) as HTMLButtonElement | null
        )?.click();
      }, id);
      const panel = page.locator("[data-evidence-panel]").first();
      await expect(panel).toBeVisible();
      // Floating InMeetingAlertCard + compact panel: footer link can sit outside the viewport
      // while still "visible" to Playwright; DOM click matches digest chip pattern in this file.
      await page.evaluate(() => {
        const root = document.querySelector("[data-evidence-panel]");
        if (!root) {
          return;
        }
        const link = Array.from(root.querySelectorAll("a")).find((a) =>
          /navigate to source/i.test(a.textContent ?? ""),
        ) as HTMLAnchorElement | undefined;
        link?.click();
      });
      await expect(page).toHaveURL(new RegExp(`/evidence/${id}`));
      await expect(page.getByRole("heading", { name: /Evidence node/i })).toBeVisible();
    });
  });

  test.describe("Story 9.1 — meeting signal + NFR1 render budget (Epic 9.1)", () => {
    test.use({
      extraHTTPHeaders: {
        "x-deployai-role": "deployment_strategist",
        "x-deployai-tenant": "00000000-0000-4000-8000-000000000001",
      },
    });

    test.afterEach(async ({ page }) => {
      await page.unroute("**/api/internal/strategist-activity*");
    });

    test("BFF inMeeting surfaces FR36 active card within 8s (single-sample NFR1)", async ({
      page,
    }) => {
      const today = new Date().toISOString().slice(0, 10);
      const oracleAt = new Date().toISOString();
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
            ingestionInProgress: false,
            controlPlane: "ok",
            strategistLocalDate: today,
            agentServiceHealth: "unconfigured",
            inMeeting: true,
            meetingId: "demo-meeting-e2e",
            meetingTitle: "E2E stub meeting (Graph calendar deferred)",
            oracleInMeetingAlertAt: oracleAt,
            meetingDetectionSource: "oracle_signal",
            calendarPollIntervalSeconds: 30,
          }),
        });
      });
      const t0 = Date.now();
      await page.goto("/in-meeting", { waitUntil: "domcontentloaded" });
      await expect(page.locator('[data-epic91-meeting-alert="active"]')).toBeVisible({
        timeout: 8000,
      });
      const elapsed = Date.now() - t0;
      expect(
        elapsed,
        `NFR1/FR36 single-sample ceiling 8s from navigation to active card (was ${elapsed}ms)`,
      ).toBeLessThanOrEqual(8000);
    });

    test("Epic 9.1 debt — lazy citation mounts ≤3s after active alert chrome", async ({ page }) => {
      const today = new Date().toISOString().slice(0, 10);
      const oracleAt = new Date().toISOString();
      const firstId = "2d4437ee-9336-441e-ab57-121b81ee57a4";
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
            ingestionInProgress: false,
            controlPlane: "ok",
            strategistLocalDate: today,
            agentServiceHealth: "unconfigured",
            inMeeting: true,
            meetingId: "demo-meeting-e2e",
            meetingTitle: "E2E stub meeting (Graph calendar deferred)",
            oracleInMeetingAlertAt: oracleAt,
            meetingDetectionSource: "oracle_signal",
            calendarPollIntervalSeconds: 30,
          }),
        });
      });
      await page.goto("/in-meeting", { waitUntil: "domcontentloaded" });
      await expect(page.locator('[data-epic91-meeting-alert="active"]')).toBeVisible({
        timeout: 8000,
      });
      const t0 = Date.now();
      await expect(page.locator(`#citation-in-meeting-${firstId}`)).toBeVisible({ timeout: 3000 });
      expect(
        Date.now() - t0,
        "lazy citation should mount within 3s of the active meeting alert",
      ).toBeLessThanOrEqual(3000);
    });

    test("Epic 9.1 debt — NFR1 p95 ≤8s over repeated navigations (EPIC91_NFR1_SAMPLES)", async ({
      page,
    }) => {
      test.setTimeout(600_000);
      const today = new Date().toISOString().slice(0, 10);
      const oracleAt = new Date().toISOString();
      const iterations = Number(process.env.EPIC91_NFR1_SAMPLES ?? (process.env.CI ? "20" : "100"));
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
            ingestionInProgress: false,
            controlPlane: "ok",
            strategistLocalDate: today,
            agentServiceHealth: "unconfigured",
            inMeeting: true,
            meetingId: "demo-meeting-e2e",
            meetingTitle: "E2E stub meeting (Graph calendar deferred)",
            oracleInMeetingAlertAt: oracleAt,
            meetingDetectionSource: "oracle_signal",
            calendarPollIntervalSeconds: 30,
          }),
        });
      });

      function p95(samples: number[]): number {
        if (samples.length === 0) {
          return 0;
        }
        const s = [...samples].sort((a, b) => a - b);
        const idx = Math.ceil(0.95 * s.length) - 1;
        return s[Math.max(0, idx)]!;
      }

      const samples: number[] = [];
      for (let i = 0; i < iterations; i++) {
        const nav0 = Date.now();
        await page.goto("/in-meeting", { waitUntil: "domcontentloaded" });
        await expect(page.locator('[data-epic91-meeting-alert="active"]')).toBeVisible({
          timeout: 8000,
        });
        samples.push(Date.now() - nav0);
      }
      const p = p95(samples);
      expect(
        p,
        `NFR1 p95 over ${iterations} navigations should be ≤8000ms (p95 was ${p}ms)`,
      ).toBeLessThanOrEqual(8000);
    });
  });

  test.describe("strategist route middleware", () => {
    for (const path of ["/digest", "/in-meeting"] as const) {
      test(`returns 403 for ${path} when x-deployai-role is missing`, async ({ page }) => {
        const r = await page.goto(path, { waitUntil: "domcontentloaded" });
        expect(r?.status(), `unauthenticated ${path} should be forbidden at edge`).toBe(403);
      });
    }
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
        "/action-queue",
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
