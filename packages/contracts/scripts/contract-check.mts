/**
 * Fails if committed JSON Schema bytes do not match a fresh Zod emit.
 * For intentional breaking changes, add `migrations/contracts/MIGRATION-*.md` and
 * bump semver / changelog (see `migrations/contracts/README.md`).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { isDeepStrictEqual } from "node:util";
import { CITATION_ENVELOPE_SCHEMA_VERSION } from "../src/citation-envelope.js";
import { buildCitationEnvelopeJsonDocument } from "./lib/build-citation-json-schema.js";

const __root = join(dirname(fileURLToPath(import.meta.url)), "..");
const committedPath = join(
  __root,
  "schema",
  `citation-envelope-${CITATION_ENVELOPE_SCHEMA_VERSION}.schema.json`,
);

const expected = buildCitationEnvelopeJsonDocument();
const onDisk = JSON.parse(readFileSync(committedPath, "utf-8")) as Record<string, unknown>;

if (!isDeepStrictEqual(expected, onDisk)) {
  process.stderr.write(
    `Schema drift: ${committedPath} does not match Zod emit. Run: cd packages/contracts && pnpm run emit-schema && pnpm exec prettier --write ${committedPath}\n`,
  );
  process.exit(1);
}

process.stdout.write("citation-envelope JSON Schema matches Zod.\n");
