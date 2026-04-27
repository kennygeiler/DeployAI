import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { appendActionQueueItems, type ActionQueueItem } from "@/lib/bff/strategist-queues-store";
import { getActorFromHeaders } from "@/lib/internal/actor";
import { MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";

type Body = {
  unattendedIds: string[];
};

/**
 * Epic 9.4 — unattended in-meeting items become Action Queue rows (`source: in_meeting_alert`).
 */
export async function POST(request: NextRequest) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  let body: Body;
  try {
    body = (await request.json()) as Body;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (!Array.isArray(body.unattendedIds)) {
    return NextResponse.json({ error: "unattendedIds array required" }, { status: 400 });
  }
  const now = new Date().toISOString();
  const rows: ActionQueueItem[] = body.unattendedIds.map((id) => {
    const row = MORNING_DIGEST_TOP.find((x) => x.id === id);
    return {
      id: `carry-${id}-${Date.now()}`,
      priority: "P2",
      phase: "P3 — Ecosystem map",
      description: row?.label ?? `Carryover from in-meeting alert (${id})`,
      status: "open",
      claimed_by: null,
      updated_at: now,
      source: "in_meeting_alert",
      evidence_node_ids: [id],
    };
  });
  appendActionQueueItems(actor.tenantId ?? null, rows);
  return NextResponse.json({ ok: true, inserted: rows.length }, { status: 200 });
}
