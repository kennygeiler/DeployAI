import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { appendActionQueueItems } from "@/lib/bff/strategist-queues-store";
import { buildInMeetingCarryoverRows } from "@/lib/epic9/in-meeting-carryover-build";
import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";
import { strategistQueuesUseControlPlane } from "@/lib/internal/strategist-queues-backend";
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
  const rows = buildInMeetingCarryoverRows(body.unattendedIds, now);
  const tid = actor.tenantId?.trim();
  if (
    strategistQueuesUseControlPlane() &&
    tid &&
    getControlPlaneBaseUrl() &&
    getControlPlaneInternalKey()
  ) {
    try {
      await cpBulkAppendActionQueue(tid, rows);
      return NextResponse.json({ ok: true, inserted: rows.length, source: "cp" }, { status: 200 });
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      return NextResponse.json({ error: msg, source: "cp_error" }, { status: 502 });
    }
  }
  appendActionQueueItems(actor.tenantId ?? null, rows);
  return NextResponse.json({ ok: true, inserted: rows.length, source: "memory" }, { status: 200 });
}
