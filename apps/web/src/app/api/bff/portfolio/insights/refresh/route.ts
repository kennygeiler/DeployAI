import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpRefreshTenantInsights } from "@/lib/internal/insights-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Phase 7 (increment 7.4) — refresh portfolio insights. Runs the Master
 * Strategist agent across all of the actor's tenant's engagements.
 * Idempotency + LLM short-circuit are CP-side.
 */
export async function POST() {
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
  const tid = actor.tenantId!.trim();
  try {
    const insights = await cpRefreshTenantInsights(tid);
    return NextResponse.json({ insights, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
