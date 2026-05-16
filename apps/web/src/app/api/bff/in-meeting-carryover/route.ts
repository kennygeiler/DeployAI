import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { buildInMeetingCarryoverRows } from "@/lib/epic9/in-meeting-carryover-build";
import { loadMorningDigestTopItemsResultForActor } from "@/lib/strategist-data/strategist-surface-data";
import { getActorFromHeaders } from "@/lib/internal/actor";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";
import { cpBulkAppendActionQueue } from "@/lib/internal/strategist-queues-cp";

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
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) return cpMisconfigured;
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
  const digestLoad = await loadMorningDigestTopItemsResultForActor(actor);
  const rows = buildInMeetingCarryoverRows(body.unattendedIds, now, {
    digest: digestLoad.items,
  });
  const tid = actor.tenantId!.trim();
  try {
    await cpBulkAppendActionQueue(tid, rows);
    return NextResponse.json({ ok: true, inserted: rows.length, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
