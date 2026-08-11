import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import {
  cpGetEngagementSummary,
  SummaryEndpointUnavailableError,
} from "@/lib/internal/engagement-summary-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Wave 2.5 U3 — engagement summary for the Brief's fast first paint.
 *
 * Proxies CP `GET /internal/v1/engagements/{id}/summary` (small payload:
 * header, members, counts, recent changes). Returns 404 when the CP does
 * not expose the endpoint yet so the client can fall back to the full
 * detail aggregate.
 */
export async function GET(_request: NextRequest, ctx: Ctx) {
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
  try {
    const summary = await cpGetEngagementSummary(tid, engagementId);
    return NextResponse.json(summary, { status: 200 });
  } catch (e) {
    if (e instanceof SummaryEndpointUnavailableError) {
      return NextResponse.json({ error: "summary endpoint unavailable" }, { status: 404 });
    }
    return nextResponseFromStrategistCpFetchError(e);
  }
}
