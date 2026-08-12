import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpExtractMatrixProposals } from "@/lib/internal/matrix-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Wave 3 K2 — run Cartographer extraction on one already-ingested canonical
 * event. The Capture flow calls /ingest (with `extract: false`) and then this
 * route, so the UI can show honest staged progress ("Saving…" → "Extracting…")
 * instead of one opaque long request. Idempotent by event id on the CP side.
 *
 * Authz: gates with `canonical:read`, matching the /ingest and
 * /extract-preview peers. That deliberately means `demo_guest` sessions can
 * trigger extraction on the demo tenant — mutations are allowed by design on
 * that disposable tenant so the guided tour's capture act works for guests
 * (see services/control-plane/.../demo_session_internal.py for the posture).
 */
export async function POST(request: NextRequest, ctx: Ctx) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", {
    kind: "canonical_memory",
    tenantId: actor.tenantId,
  });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return cpMisconfigured;
  }
  const { engagementId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  let parsed: { event_id?: unknown; force?: unknown };
  try {
    parsed = (await request.json()) as typeof parsed;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const eventId = typeof parsed.event_id === "string" ? parsed.event_id.trim() : "";
  if (!eventId) {
    return NextResponse.json({ error: "event_id is required" }, { status: 400 });
  }
  const force = parsed.force === true;
  try {
    const proposals = await cpExtractMatrixProposals(tid, engagementId, eventId, { force });
    return NextResponse.json({ proposals, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
