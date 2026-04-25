#!/usr/bin/env node
/**
 * Build ≥200 `gen-*.yaml` query files: 21-cell matrix coverage, first 50 rule-evaluable, rest `judge_only` (4-4).
 */
import { mkdir, readdir, unlink, writeFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import yaml from "js-yaml";

import { PHASES, TOPOLOGIES, cellKey } from "./constants.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = join(__dirname, "..", "golden", "queries");
const TARGET = 200;
const JUDGE_ONLY_AFTER = 50;

await mkdir(OUT, { recursive: true });

const cells = [];
for (const p of PHASES) for (const t of TOPOLOGIES) cells.push([p, t]);

const rows = [];
for (let n = 1; n <= TARGET; n++) {
  const [phase, topology] = cells[(n - 1) % cells.length];
  const highConf = n <= JUDGE_ONLY_AFTER;
  rows.push({ query_id: `gen-${String(n).padStart(4, "0")}`, phase, topology, highConf, n });
}

for (const name of await readdir(OUT)) {
  if (name.startsWith("gen-") && (name.endsWith(".yaml") || name.endsWith(".yml")))
    await unlink(join(OUT, name));
}

for (const r of rows) {
  const doc = {
    query_id: r.query_id,
    phase: r.phase,
    stakeholder_topology: r.topology,
    query_text: `Synthetic ${r.query_id} for ${cellKey(r.phase, r.topology)} (bulk corpus).`,
    tenant_scenario: ["default", "federal", "municipal", "contractor", "tribal"][r.n % 5],
    judge_only: !r.highConf,
  };
  if (r.highConf) {
    doc.expected_citations = [
      { node_id: randomUUID(), must_appear: true, rank_floor: 0 },
    ];
  } else {
    doc.expected_citations = [];
  }
  await writeFile(join(OUT, `${r.query_id}.yaml`), yaml.dump(doc, { lineWidth: 120, noRefs: true }), "utf8");
}

console.log(`expand-corpus: wrote ${rows.length} files → ${OUT}`);
