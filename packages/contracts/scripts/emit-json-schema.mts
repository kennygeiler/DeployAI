/**
 * Emit JSON Schema (draft 2020-12) for the citation envelope from Zod.
 * Run after changing `citation-envelope.ts`; commit the updated `schema/*.json`.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { CITATION_ENVELOPE_SCHEMA_VERSION } from "../src/citation-envelope.js";
import { buildCitationEnvelopeJsonDocument } from "./lib/build-citation-json-schema.js";

const __root = dirname(fileURLToPath(import.meta.url));
const outDir = join(__root, "..", "schema");
const outFile = join(outDir, `citation-envelope-${CITATION_ENVELOPE_SCHEMA_VERSION}.schema.json`);

const document = buildCitationEnvelopeJsonDocument();

mkdirSync(outDir, { recursive: true });
writeFileSync(outFile, `${JSON.stringify(document, null, 2)}\n`, "utf-8");
// eslint-disable-next-line no-console
console.info(`Wrote ${outFile}`);
