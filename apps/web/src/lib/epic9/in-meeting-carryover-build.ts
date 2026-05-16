import type { ActionQueueItem } from "@/lib/bff/strategist-queue-types";
import type {
  DigestRankedOutItem,
  DigestTopItem,
} from "@/lib/strategist-data/strategist-surface-types";

export type CarryoverDigestContext = {
  digest?: readonly DigestTopItem[];
  rankedOut?: readonly DigestRankedOutItem[];
};

/** Resolve a human description for carryover rows (digest primaries + optional ranked-out labels). */
export function digestLabelForCarryoverId(
  id: string,
  ctx: CarryoverDigestContext = {},
): string | undefined {
  const top = ctx.digest?.find((x) => x.id === id);
  if (top) {
    return top.label;
  }
  const ranked = ctx.rankedOut?.find((x) => x.id === id);
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
  ctx: CarryoverDigestContext = {},
): ActionQueueItem[] {
  return unattendedIds.map((id, i) => ({
    id: `carry-${id}-${i}-${nowIso}`,
    priority: "P2",
    phase: "P3 — Ecosystem map",
    description: digestLabelForCarryoverId(id, ctx) ?? `Carryover from in-meeting alert (${id})`,
    status: "open",
    claimed_by: null,
    updated_at: nowIso,
    source: "in_meeting_alert",
    evidence_node_ids: [id],
  }));
}
