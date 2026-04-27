import type { DigestTopItem } from "@/lib/epic8/mock-digest";
import { buildPhaseTrackingRows } from "@/lib/epic8/mock-digest";
import { getStrategistLocalDateForServer } from "@/lib/internal/strategist-local-date";

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
 * In-process mock for canonical search until a dedicated search service exists.
 * Matches label, citation id, and phase strings.
 */
export function searchMemoryMock(
  q: string,
  digest: ReadonlyArray<DigestTopItem>,
  strategistLocalDate: string,
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
  for (const r of buildPhaseTrackingRows(strategistLocalDate)) {
    const txt = norm(`${r.title} ${r.id} ${r.summary} ${r.bodyText} ${r.phase} ${r.assignee}`);
    if (txt.includes(nq)) {
      out.push({ id: r.id, label: r.title, kind: "action_queue", queryText: txt });
    }
  }
  return out.slice(0, 50);
}

export function searchMemoryMockForServer(
  q: string,
  digest: ReadonlyArray<DigestTopItem>,
): MemorySearchHit[] {
  return searchMemoryMock(q, digest, getStrategistLocalDateForServer());
}
