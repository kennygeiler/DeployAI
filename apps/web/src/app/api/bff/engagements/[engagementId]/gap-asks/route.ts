import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpGetGapAsks, GapAsksEndpointUnavailableError } from "@/lib/internal/gap-asks-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Wave 5 GA2 — "Kenny asks" for the Brief's Needs-you region.
 *
 * Proxies CP `GET /internal/v1/engagements/{id}/gap-asks` (deterministic
 * gap detection, dismissed/snoozed asks already filtered). Returns 404 when
 * the CP does not expose the endpoint yet so the card group can stay quiet.
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
    const asks = await cpGetGapAsks(tid, engagementId);
    return NextResponse.json({ asks }, { status: 200 });
  } catch (e) {
    if (e instanceof GapAsksEndpointUnavailableError) {
      return NextResponse.json({ error: "gap-asks endpoint unavailable" }, { status: 404 });
    }
    return nextResponseFromStrategistCpFetchError(e);
  }
}
