import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { pushInMeetingAudit } from "@/lib/bff/strategist-queues-store";
import { auditTypeForInMeetingAction } from "@/lib/epic9/in-meeting-alert-actions";
import { getActorFromHeaders } from "@/lib/internal/actor";

type Body = {
  itemId: string;
  action: "dismiss" | "correct";
};

/**
 * Epic 9.3 — records `alert.dismissed` / `alert.corrected` (BFF mock; canonical audit lands on CP).
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
  if (!body.itemId || (body.action !== "dismiss" && body.action !== "correct")) {
    return NextResponse.json(
      { error: "itemId and action dismiss|correct required" },
      { status: 400 },
    );
  }
  const type = auditTypeForInMeetingAction(body.action);
  pushInMeetingAudit(actor.tenantId ?? null, { type, itemId: body.itemId });
  return NextResponse.json({ ok: true, type }, { status: 200 });
}
