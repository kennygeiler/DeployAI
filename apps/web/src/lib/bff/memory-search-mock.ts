import type { ActionQueueRow, DigestTopItem } from "@/lib/strategist-data/strategist-surface-types";

export type MemorySearchHit = {
  id: string;
  label: string;
  kind: "digest" | "action_queue";
  /** Snippet for cmdk / palette */
  queryText: string;
};

function norm(s: string): string {
  return s.toLowerCase().replace(/\s+/g, " ").trim();
}

/**
 * In-process search until a dedicated search service exists.
 * Matches label, citation id, and phase strings over caller-supplied rows (no fixtures).
 */
export function searchMemoryMock(
  q: string,
  digest: ReadonlyArray<DigestTopItem>,
  phaseRows: ReadonlyArray<ActionQueueRow>,
): MemorySearchHit[] {
  const nq = norm(q);
  if (nq.length < 1) {
    return [];
  }
  const out: MemorySearchHit[] = [];
  for (const d of digest) {
    const txt = norm(
      `${d.label} ${d.preview.citationId} ${d.preview.retrievalPhase} ${d.bodyText}`,
    );
    if (txt.includes(nq)) {
      out.push({ id: d.id, label: d.label, kind: "digest", queryText: txt });
    }
  }
  for (const r of phaseRows) {
    const txt = norm(`${r.title} ${r.id} ${r.summary} ${r.bodyText} ${r.phase} ${r.assignee}`);
    if (txt.includes(nq)) {
      out.push({ id: r.id, label: r.title, kind: "action_queue", queryText: txt });
    }
  }
  return out.slice(0, 50);
}
