import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const _dir = dirname(fileURLToPath(import.meta.url));

export type Corpus = {
  version: number;
  tenants: string[];
  phases: string[];
  nodes: { id: string; tenantIndex: number; phaseIndex: number; label: string }[];
  contextByNodeId: Record<
    string,
    { stakeholderPeers: string[]; activeBlockers: string[]; recentEvents: string[] }
  >;
};

export const corpus: Corpus = JSON.parse(
  readFileSync(join(_dir, "..", "fixtures", "corpus.json"), "utf-8"),
) as Corpus;
