import type { MemorySearchHit } from "./memory-search-mock";

/**
 * Tolerate mock BFF, proxied services, and minor shape drift (`results` instead of `hits`).
 */
export function parseStrategistMemorySearchResponse(data: unknown): {
  hits: MemorySearchHit[];
  source: string;
} {
  if (!data || typeof data !== "object") {
    return { hits: [], source: "unknown" };
  }
  const o = data as Record<string, unknown>;
  const source = typeof o.source === "string" ? o.source : "unknown";
  const raw = o.hits ?? o.results;
  if (!Array.isArray(raw)) {
    return { hits: [], source };
  }
  const hits: MemorySearchHit[] = [];
  for (const x of raw) {
    if (!x || typeof x !== "object") {
      continue;
    }
    const h = x as Record<string, unknown>;
    const id = typeof h.id === "string" ? h.id : null;
    const label = typeof h.label === "string" ? h.label : null;
    if (!id || !label) {
      continue;
    }
    const kind = h.kind === "digest" || h.kind === "action_queue" ? h.kind : "digest";
    const queryText = typeof h.queryText === "string" ? h.queryText : label;
    hits.push({ id, label, kind, queryText });
  }
  return { hits, source };
}
