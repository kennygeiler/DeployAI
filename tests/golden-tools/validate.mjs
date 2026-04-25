#!/usr/bin/env node
/**
 * `pnpm run golden:validate` — assert every query YAML matches the golden schema
 * and the 21-cell matrix has ≥1 query (Story 4-3, NFR50/NFR53).
 */
import { readFile, readdir } from "node:fs/promises";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import yaml from "js-yaml";

import { PHASES, TOPOLOGIES, cellKey } from "./constants.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const QUERIES_DIR = join(__dirname, "..", "golden", "queries");

const REQUIRED = [
  "query_id",
  "phase",
  "stakeholder_topology",
  "query_text",
  "expected_citations",
];

function isObject(x) {
  return x != null && typeof x === "object" && !Array.isArray(x);
}

function err(msg) {
  console.error(`golden:validate — ${msg}`);
  process.exit(1);
}

function assertPhase(p) {
  if (!PHASES.includes(p)) err(`invalid phase ${JSON.stringify(p)}`);
}
function assertTopo(t) {
  if (!TOPOLOGIES.includes(t)) err(`invalid stakeholder_topology ${JSON.stringify(t)}`);
}

let files = 0;
const cells = new Set();

for (const name of await readdir(QUERIES_DIR)) {
  if (!name.endsWith(".yaml") && !name.endsWith(".yml")) continue;
  files++;
  const raw = await readFile(join(QUERIES_DIR, name), "utf8");
  let doc;
  try {
    doc = yaml.load(raw);
  } catch (e) {
    err(`${name}: YAML parse: ${e}`);
  }
  if (!isObject(doc)) err(`${name}: root must be a mapping`);
  for (const k of REQUIRED) {
    if (doc[k] == null) err(`${name}: missing field ${k}`);
  }
  if (typeof doc.query_id !== "string" || !doc.query_id.length) err(`${name}: query_id must be a non-empty string`);
  if (typeof doc.query_text !== "string") err(`${name}: query_text must be a string`);
  assertPhase(doc.phase);
  assertTopo(doc.stakeholder_topology);
  if (!Array.isArray(doc.expected_citations)) {
    err(`${name}: expected_citations must be an array`);
  }
  const jOnly = doc.judge_only === true;
  if (!jOnly && doc.expected_citations.length < 1) {
    err(`${name}: expected_citations must be non-empty when judge_only is not true`);
  }
  for (const [i, ec] of doc.expected_citations.entries()) {
    if (!isObject(ec)) err(`${name}: expected_citations[${i}] not an object`);
    if (typeof ec.node_id !== "string") err(`${name}: expected_citations[${i}].node_id required`);
    if (typeof ec.must_appear !== "boolean") err(`${name}: expected_citations[${i}].must_appear must be boolean`);
    if (typeof ec.rank_floor !== "number" || !Number.isInteger(ec.rank_floor) || ec.rank_floor < 0) {
      err(`${name}: expected_citations[${i}].rank_floor must be a non-negative integer`);
    }
  }
  if (doc.judge_only != null && typeof doc.judge_only !== "boolean") err(`${name}: judge_only must be boolean`);
  cells.add(cellKey(doc.phase, doc.stakeholder_topology));
}

if (files < 1) err(`no query YAML files in ${QUERIES_DIR}`);

const expected = PHASES.length * TOPOLOGIES.length;
if (cells.size < expected) {
  const want = new Set();
  for (const p of PHASES) for (const t of TOPOLOGIES) want.add(cellKey(p, t));
  for (const c of want) {
    if (!cells.has(c)) err(`21-cell matrix missing cell: ${c}`);
  }
}

console.log(
  `golden:validate — ok (${files} files, 21/21 matrix cells present, ${cells.size} unique cells)`,
);
process.exit(0);
