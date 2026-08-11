import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpDismissMatrixInsight, cpPatchTemporalInsightStatus } from "@/lib/internal/insights-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string; insightId: string }> };

/**
 * Phase 7 (increment 7.3) — dismiss an insight. Pilot-refresh F2 extends
 * this to both insight models: `?model=temporal` patches the temporal row's
 * status; the default (`matrix`) keeps the Oracle behavior, where dismissed
 * rows are never re-surfaced on refresh (design §11). The acting user's id
 * is taken from the server-side actor.
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
  const { engagementId, insightId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  const actorId = await getActorIdFromHeaders();
  const model = request.nextUrl.searchParams.get("model") ?? "matrix";
  if (model !== "matrix" && model !== "temporal") {
    return NextResponse.json({ error: "invalid model" }, { status: 400 });
  }
  try {
    if (model === "temporal") {
      const insight = await cpPatchTemporalInsightStatus(tid, insightId, "dismissed");
      return NextResponse.json({ insight, source: "cp" }, { status: 200 });
    }
    const insight = await cpDismissMatrixInsight(tid, engagementId, insightId, {
      actor_id: actorId,
    });
    return NextResponse.json({ insight, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
