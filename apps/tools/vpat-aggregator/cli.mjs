#!/usr/bin/env node
/**
 * VPAT evidence stub — merges references to local artifact paths. Real pipeline:
 *  - Ingest `storybook` axe JSON, `a11y.yml` Playwright, `pa11y` if present.
 *  - S3 upload + 7y retention: wire in `vpat-evidence.yml` with AWS OIDC.
 *
 * @see docs/design-system/governance.md
 */
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const slug = (process.env.VPAT_VERSION ?? "dev").replace(/[^\w.\-]+/g, "_");
const out =
  process.env.VPAT_OUT ?? join(__dirname, "../../../artifacts/vpat", `evidence-${slug}.json`);
const version = process.env.VPAT_VERSION ?? "0.0.0-dev";

const payload = {
  schema: "deployai.vpat.v0",
  version,
  generatedAt: new Date().toISOString(),
  sources: {
    storybookA11y: process.env.VPAT_STORYBOOK_AXE ?? null,
    playwrightAxe: process.env.VPAT_PLAYWRIGHT_AXE ?? null,
    pa11y: process.env.VPAT_PA11Y ?? null,
  },
  notes:
    "Populate VPAT_SARIF_GLOB and CI artifact downloads before release. S3: set AWS role + bucket in vpat-evidence workflow.",
};

await mkdir(dirname(out), { recursive: true });
await writeFile(out, JSON.stringify(payload, null, 2), "utf8");
console.log(`vpat-aggregate: wrote ${out}`);
