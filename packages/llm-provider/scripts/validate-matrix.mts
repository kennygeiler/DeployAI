/**
 * Verifies the StubLlmProvider (and thus the matrix shape) covers every
 * agent in `services/config/llm-capability-matrix.yaml`.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { load } from "js-yaml";
import { createStubLlmProvider } from "../src/stub-provider.js";

const _root = dirname(fileURLToPath(import.meta.url));
const matrixPath = join(
  _root,
  "..",
  "..",
  "..",
  "services",
  "config",
  "llm-capability-matrix.yaml",
);
const raw = readFileSync(matrixPath, "utf-8");
const doc = load(raw) as {
  version: number;
  agents: Record<string, { require: string[] }>;
};

const p = createStubLlmProvider();
const caps = p.capabilities();

let failed = false;
for (const [name, def] of Object.entries(doc.agents)) {
  for (const k of def.require) {
    if (caps[k as keyof typeof caps] !== true) {
      process.stderr.write(
        `llm matrix: agent "${name}" needs capability ${k} but ${p.id} reports ${String(caps[k as keyof typeof caps])}\n`,
      );
      failed = true;
    }
  }
}

if (failed) {
  process.exit(1);
}
process.stdout.write("llm-capability-matrix: all agent requirements met by stub provider.\n");
