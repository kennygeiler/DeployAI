#!/usr/bin/env node
/**
 * Scaffold a new query file: pnpm run golden:author -- --id q-001 --phase discovery --topo single_stakeholder
 */
import { writeFile } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { randomUUID } from "node:crypto";
import yaml from "js-yaml";

import { PHASES, TOPOLOGIES } from "./constants.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = join(__dirname, "..", "golden", "queries");

function arg(name) {
  const i = process.argv.indexOf(name);
  return i >= 0 && i + 1 < process.argv.length ? process.argv[i + 1] : null;
}

const id = arg("--id");
const phase = arg("--phase");
const topo = arg("--topo");
if (!id || !phase || !topo) {
  console.error("Usage: node author.mjs -- --id <query_id> --phase <phase> --topo <stakeholder_topology>");
  console.error(`phase ∈ ${PHASES.join(", ")}`);
  console.error(`topo ∈ ${TOPOLOGIES.join(", ")}`);
  process.exit(1);
}
if (!PHASES.includes(phase) || !TOPOLOGIES.includes(topo)) {
  console.error("Invalid phase or topology");
  process.exit(1);
}

const doc = {
  query_id: id,
  phase,
  stakeholder_topology: topo,
  query_text: "EDITME: author your query here (tenant-scoped, phase-appropriate).",
  tenant_scenario: "default",
  judge_only: false,
  expected_citations: [
    {
      node_id: randomUUID(),
      must_appear: true,
      rank_floor: 0,
    },
  ],
};

const outPath = join(OUT, `${id}.yaml`);
await writeFile(outPath, yaml.dump(doc, { lineWidth: 120, noRefs: true }), "utf8");
console.log(`Wrote ${outPath}`);
