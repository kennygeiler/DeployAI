import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpDismissTenantInsight } from "@/lib/internal/insights-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ insightId: string }> };

/**
 * Phase 7 (increment 7.4) — dismiss a portfolio (tenant-scoped) insight.
 * Dismissed rows never re-surface on subsequent refresh.
 */
export async function POST(_request: NextRequest, ctx: Ctx) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return cpMisconfigured;
  }
  const { insightId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  const actorId = await getActorIdFromHeaders();
  try {
    const insight = await cpDismissTenantInsight(tid, insightId, { actor_id: actorId });
    return NextResponse.json({ insight, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
