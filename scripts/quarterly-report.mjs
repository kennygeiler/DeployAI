#!/usr/bin/env node
/**
 * Generate a short Epic 4 quarterly report from `sprint-status.yaml` (no YAML dependency).
 * Writes: artifacts/quarterly/report-<year>-Q<q>.md
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");
const statusPath = join(root, "_bmad-output/implementation-artifacts/sprint-status.yaml");
const outDir = join(root, "artifacts/quarterly");

const text = readFileSync(statusPath, "utf8");
const now = new Date();
const y = now.getUTCFullYear();
const m = now.getUTCMonth() + 1;
const q = Math.ceil(m / 3);
const outFile = join(outDir, `report-${y}-Q${q}.md`);

const lines = text.split("\n");
const epic4 = Object.create(null);
let inEpic4 = false;
for (const line of lines) {
  if (line.match(/^\s*#\s*Epic 4:/)) {
    inEpic4 = true;
    continue;
  }
  if (line.match(/^\s*#\s*Epic 5:/)) {
    inEpic4 = false;
    break;
  }
  if (inEpic4) {
    const mEpic = line.match(/^\s+(epic-4):\s*(\S+)/);
    if (mEpic) {
      epic4[mEpic[1]] = mEpic[2];
      continue;
    }
    const m2 = line.match(/^\s+(4-\d+[^:]+):\s*(\S+)/);
    if (m2) {
      epic4[m2[1].trimEnd()] = m2[2];
    }
  }
}

const rows = Object.entries(epic4)
  .filter(([k]) => k.startsWith("4-") || k === "epic-4")
  .sort((a, b) => {
    if (a[0] === "epic-4") {
      return -1;
    }
    if (b[0] === "epic-4") {
      return 1;
    }
    return a[0].localeCompare(b[0]);
  })
  .map(([k, v]) => `| \`${k}\` | ${v} |`)
  .join("\n");

const body = [
  `# DeployAI — quarterly snapshot (${y} Q${q})`,
  "",
  "## Epic 4 — agent runtime & replay harness",
  "",
];
body.push("Generated from `sprint-status.yaml` (stories 4-1+).", "");
if (rows) {
  body.push("| Story | Status |", "| --- | --- |", rows, "");
} else {
  body.push("_(No 4-x rows parsed — check file path.)_", "");
}
body.push(`_Generated at ${now.toISOString()}_`, "");

mkdirSync(outDir, { recursive: true });
writeFileSync(outFile, body.join("\n"), "utf8");
process.stdout.write(`${outFile}\n`);
