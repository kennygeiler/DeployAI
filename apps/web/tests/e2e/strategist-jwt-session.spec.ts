import { expect, test } from "@playwright/test";

import { mintPilotAccessJwt } from "./fixtures/mint-pilot-access-jwt";

const PILOT_TID = "33333333-3333-4333-8333-333333333333";

/**
 * Story 15.1: production-style `next start` derives role + tenant from a CP-shaped access JWT
 * (cookie) so callers do not send `x-deployai-*` manually.
 *
 * When `reuseExistingServer` skips Playwright env injection, this suite self-skips if the
 * running server does not trust the fixture signing key.
 */
test.describe("Story 15.1 — strategist session from access JWT", () => {
  test.beforeAll(async ({ request }) => {
    const jwt = await mintPilotAccessJwt({
      sub: "playwright-15-1",
      tid: PILOT_TID,
      roles: ["deployment_strategist"],
    });
    const res = await request.get("/digest", {
      headers: { Cookie: `deployai_access_token=${jwt}` },
    });
    test.skip(
      !res.ok(),
      "Web server must run with DEPLOYAI_WEB_TRUST_JWT=1 and apps/web/tests/e2e/fixtures pilot public PEM (CI webServer or match locally).",
    );
  });

  test("cookie JWT → digest + BFF action-queue without x-deployai-* headers", async ({
    page,
    context,
  }) => {
    const jwt = await mintPilotAccessJwt({
      sub: "playwright-15-1",
      tid: PILOT_TID,
      roles: ["deployment_strategist"],
    });
    await context.addCookies([
      {
        name: "deployai_access_token",
        value: jwt,
        url: "http://127.0.0.1:3000",
      },
    ]);
    await page.goto("/digest", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /Morning digest/i })).toBeVisible();

    const bff = await page.evaluate(async () => {
      const r = await fetch("/api/bff/action-queue");
      const body = r.ok ? await r.json() : null;
      return { status: r.status, body };
    });
    expect(bff.status).toBe(200);
    expect(Array.isArray(bff.body?.items)).toBe(true);
  });
});
