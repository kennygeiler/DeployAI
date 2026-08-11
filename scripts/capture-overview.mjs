#!/usr/bin/env node
/**
 * Capture the product screenshots used by the /overview walkthrough page.
 *
 * Usage:
 *   OVERVIEW_BASE_URL=http://localhost:3000 node scripts/capture-overview.mjs
 *
 * Prerequisites:
 *   - The web dev server running with dev role injection enabled
 *     (DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1) and pointed at a control plane
 *     with the BlueState seed data loaded.
 *   - Playwright chromium (already a devDependency of @deployai/web).
 *
 * Output: apps/web/public/overview/*.png (overwrites existing files).
 */
import { mkdir, readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// @playwright/test lives in apps/web's dependency tree, not the repo root,
// so resolve it from there regardless of where this script is invoked.
const repoRoot = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const webRequire = createRequire(path.join(repoRoot, "apps", "web", "package.json"));
const playwright = await import(pathToFileURL(webRequire.resolve("@playwright/test")).href);
const chromium = playwright.chromium ?? playwright.default.chromium;

const BASE = process.env.OVERVIEW_BASE_URL ?? "http://localhost:3000";
const TENANT = process.env.OVERVIEW_TENANT_ID ?? "11111111-1111-1111-1111-111111111111";

// Seeded engagements (see control-plane seed): the XL long-cycle deal has the
// densest graph; the Member Portal Replatform is the small 26-week deal; the
// Bayview engagement carries a pending extraction proposal for the
// Needs-you / Review-inbox shots.
const ENGAGEMENT_XL = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";
const ENGAGEMENT_SMALL = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
const ENGAGEMENT_WITH_PROPOSALS = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";

const OUT_DIR = path.join(repoRoot, "apps", "web", "public", "overview");

const SETTLE_MS = 1500;

async function settle(page, ms = SETTLE_MS) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(ms);
}

async function shoot(page, name) {
  // Hide the Next.js dev-tools indicator so it does not photobomb the shot.
  await page
    .addStyleTag({ content: "nextjs-portal { display: none !important; }" })
    .catch(() => {});
  const file = path.join(OUT_DIR, `${name}.png`);
  await page.screenshot({ path: file });
  console.log(`captured ${name}.png`);
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    deviceScaleFactor: 2,
    colorScheme: "light",
    extraHTTPHeaders: {
      "x-deployai-role": "deployment_strategist",
      "x-deployai-tenant": TENANT,
      // A seeded engagement member (Jordan Park). Chat persistence has a
      // foreign key on the acting user, and the default dev fallback actor
      // id is not present in the seeded users table.
      "x-deployai-actor-id": "aaaaaaa2-2222-4222-8222-222222222222",
    },
  });
  const page = await context.newPage();

  // (a) Portfolio — attention-ranked engagement list.
  await page.goto(`${BASE}/engagements`);
  await page
    .getByRole("link", { name: /BlueState Health/ })
    .first()
    .waitFor({ timeout: 30_000 });
  await settle(page, 2500);
  await shoot(page, "portfolio");

  // (b) The Brief on the XL engagement — header + Since you last looked.
  await page.goto(`${BASE}/engagements/${ENGAGEMENT_XL}`);
  await page.getByTestId("brief-header").waitFor({ timeout: 30_000 });
  await settle(page, 2500);
  await shoot(page, "brief-since-you-last-looked");

  // (g) Graph lens on the XL engagement: switch the matrix to graph view and
  // wait for the focused neighborhood + lens toolbar to render.
  await page
    .getByRole("group", { name: "Matrix view mode" })
    .getByRole("button", { name: "Graph" })
    .click();
  await page.getByTestId("matrix-graph").waitFor({ timeout: 30_000 });
  // Frame the shot around the lens toolbar + graph canvas: put the
  // "Deployment matrix" heading at the top of the viewport.
  await page
    .getByRole("heading", { name: "Deployment matrix" })
    .evaluate((el) => el.scrollIntoView({ block: "start" }));
  await settle(page, 2500);
  await shoot(page, "graph-lens");

  // (c) Needs-you queue with a pending extraction proposal card.
  await page.goto(`${BASE}/engagements/${ENGAGEMENT_WITH_PROPOSALS}`);
  await page.getByTestId("brief-header").waitFor({ timeout: 30_000 });
  await settle(page, 2500);
  await page.getByRole("heading", { name: "Needs you" }).scrollIntoViewIfNeeded();
  await page.waitForTimeout(500);
  await shoot(page, "needs-you-queue");

  // (d) Ask-bar with suggested questions on the small BlueState engagement.
  await page.goto(`${BASE}/engagements/${ENGAGEMENT_SMALL}`);
  await page.getByTestId("brief-header").waitFor({ timeout: 30_000 });
  await settle(page, 2500);
  await page.getByLabel("Ask Agent Kenny").click();
  await page.waitForTimeout(300);
  await shoot(page, "ask-bar");

  // (e) Kenny chat overlay with a streamed answer + citation chips. The
  // answer streams from the live agent, so give it a generous timeout.
  //
  // The client only calls the v2 (LangGraph) stream endpoint when the build
  // was made with NEXT_PUBLIC_AGENT_KENNY_V2_ENABLED=1; otherwise it falls
  // back to the retired v1 stream, which 5xxs against current control
  // planes. The request bodies are identical, so when the dev server was
  // built without the flag we transparently re-route v1 -> v2 here.
  await context.route("**/oracle/chat/stream", async (route) => {
    const response = await route.fetch({
      url: route.request().url().replace("/oracle/chat/stream", "/oracle/chat/stream-v2"),
      timeout: 180_000,
    });
    await route.fulfill({ response });
  });
  const question = "What led to the identity-provider decision? Cite the evidence.";
  await page.getByLabel("Ask Agent Kenny").fill(question);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await page.getByTestId("oracle-chat-panel").waitFor({ timeout: 15_000 });

  // The model does not include verifiable [kind:UUID] markers on every
  // reply (and occasionally truncates), so retry with a fresh conversation
  // until the verified-citation chips render. "Clear" resets the transcript
  // so the final capture shows a single clean question and answer.
  let gotCitations = false;
  for (let attempt = 1; attempt <= 5 && !gotCitations; attempt++) {
    if (attempt > 1) {
      // Let any still-running turn finish (the composer is disabled while
      // a reply streams), then reset to a fresh conversation and re-ask.
      // Later attempts spell out the citation-marker format — it measurably
      // raises the odds the model emits verifiable [kind:UUID] citations.
      const retryQuestion =
        attempt <= 3
          ? question
          : "What led to the identity-provider decision? Cite each claim with [event:UUID] or [node:UUID] markers.";
      const composer = page.getByLabel("Message Agent Kenny");
      for (let i = 0; i < 30 && !(await composer.isEnabled()); i++) {
        await page.waitForTimeout(2000);
      }
      const clearButton = page.getByRole("button", { name: "Clear" });
      if (await clearButton.isEnabled()) {
        await clearButton.click();
      }
      await composer.fill(retryQuestion);
      await page.getByRole("button", { name: "Send" }).click();
    }
    // Poll until either citation chips render or the turn settles without
    // them (composer re-enables on completion AND on failure rollback, so
    // budget-exhausted attempts fail fast instead of eating the timeout).
    const citationsVisible = async () =>
      (await page.getByTestId("oracle-chat-citations").count()) > 0;
    for (let tick = 0; tick < 60; tick++) {
      await page.waitForTimeout(2000);
      if (await citationsVisible()) {
        gotCitations = true;
        break;
      }
      if (tick >= 2 && (await page.getByLabel("Message Agent Kenny").isEnabled())) {
        await page.waitForTimeout(1500);
        gotCitations = await citationsVisible();
        break;
      }
    }
  }
  if (!gotCitations) {
    // Live attempts failed (typically the tenant's daily LLM budget is
    // exhausted, or the model refused to emit citation markers). Fall back
    // to replaying a real stream captured from the live agent on this same
    // engagement (scripts/fixtures/agent-kenny-okta-stream.sse) so the shot
    // still shows genuine agent output with the full reasoning trace.
    console.warn("no verified-citation chips from live attempts — replaying captured stream");
    const fixture = await readFile(
      path.join(repoRoot, "scripts", "fixtures", "agent-kenny-okta-stream.sse"),
      "utf8",
    );
    await context.unroute("**/oracle/chat/stream");
    for (const pattern of ["**/oracle/chat/stream", "**/oracle/chat/stream-v2"]) {
      await context.route(pattern, async (route) => {
        await route.fulfill({
          status: 200,
          headers: { "content-type": "text/event-stream" },
          body: fixture,
        });
      });
    }
    const composer = page.getByLabel("Message Agent Kenny");
    for (let i = 0; i < 30 && !(await composer.isEnabled()); i++) {
      await page.waitForTimeout(2000);
    }
    const clearButton = page.getByRole("button", { name: "Clear" });
    if (await clearButton.isEnabled()) {
      await clearButton.click();
    }
    await composer.fill("What led to the identity-provider decision?");
    await page.getByRole("button", { name: "Send" }).click();
    await page
      .getByTestId("oracle-chat-panel")
      .getByTestId("oracle-message")
      .nth(1)
      .waitFor({ timeout: 30_000 });
  }
  await page.waitForTimeout(2000);
  await shoot(page, "kenny-chat-answer");

  // (f) Citation receipts: open the identity-provider decision node in the
  // graph and show its Provenance tab (the upstream causal chain walked from
  // the ledger). Reload first so the chat overlay and its state are gone.
  await page.goto(`${BASE}/engagements/${ENGAGEMENT_SMALL}`);
  await page.getByTestId("brief-header").waitFor({ timeout: 30_000 });
  await settle(page, 2000);
  await page
    .getByRole("group", { name: "Matrix view mode" })
    .getByRole("button", { name: "Graph" })
    .click();
  await page.getByTestId("matrix-graph").waitFor({ timeout: 30_000 });
  await settle(page, 1500);
  // This engagement sits under the 60-node lens threshold, so the full
  // graph renders (no lens search). Find the decision node id from the
  // matrix payload and click its rendered node directly.
  const detail = await (
    await context.request.get(`${BASE}/api/bff/engagements/${ENGAGEMENT_SMALL}`)
  ).json();
  const decision = (detail?.matrix?.nodes ?? []).find(
    (n) => n.node_type === "decision" && /Okta over Auth0/.test(n.title),
  );
  if (!decision) throw new Error("identity-provider decision node not found in matrix");
  await page.locator(`.react-flow__node[data-id="${decision.id}"]`).click();
  await page.getByTestId("matrix-node-detail").waitFor({ timeout: 15_000 });
  await page.getByRole("tab", { name: "Provenance" }).click();
  await page.getByTestId("provenance-tree").waitFor({ timeout: 20_000 });
  // Expand the upstream causal chain so the receipts are actually visible.
  const expand = page.getByRole("button", { name: "Expand upstream events" }).first();
  if (await expand.count()) {
    await expand.click();
  }
  await settle(page, 1500);
  await shoot(page, "citation-evidence-panel");
  await page.keyboard.press("Escape");

  // (h) Review inbox filtered to the engagement with a pending proposal.
  await page.goto(`${BASE}/review`);
  await page.getByRole("heading", { name: "Review inbox" }).waitFor({ timeout: 30_000 });
  await settle(page, 2000);
  await page.locator("#review-filter-engagement").selectOption(ENGAGEMENT_WITH_PROPOSALS);
  await settle(page, 2000);
  await shoot(page, "review-inbox");

  await browser.close();
  console.log(`done — screenshots in ${OUT_DIR}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
