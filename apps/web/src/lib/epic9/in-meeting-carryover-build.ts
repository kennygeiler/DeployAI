import type { ActionQueueItem } from "@/lib/bff/strategist-queues-store";
import { MORNING_DIGEST_RANKED_OUT, MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";

/** Resolve a human description for carryover rows (digest primaries + ranked-out labels). */
export function digestLabelForCarryoverId(id: string): string | undefined {
  const top = MORNING_DIGEST_TOP.find((x) => x.id === id);
  if (top) {
    return top.label;
  }
  const ranked = MORNING_DIGEST_RANKED_OUT.find((x) => x.id === id);
  if (ranked) {
    return `${ranked.label} (${ranked.reason})`;
  }
  return undefined;
}

/**
 * Epic 9.4 — build Action Queue rows for unattended in-meeting primaries.
 * Stable unique ids: avoids `Date.now()` collisions when inserting multiple rows in one tick.
 */
export function buildInMeetingCarryoverRows(
  unattendedIds: string[],
  nowIso: string,
): ActionQueueItem[] {
  return unattendedIds.map((id, i) => ({
    id: `carry-${id}-${i}-${nowIso}`,
    priority: "P2",
    phase: "P3 — Ecosystem map",
    description: digestLabelForCarryoverId(id) ?? `Carryover from in-meeting alert (${id})`,
    status: "open",
    claimed_by: null,
    updated_at: nowIso,
    source: "in_meeting_alert",
    evidence_node_ids: [id],
  }));
}
