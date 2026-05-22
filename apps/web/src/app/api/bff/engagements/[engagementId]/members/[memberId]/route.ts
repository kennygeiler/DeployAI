import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpRemoveEngagementMember } from "@/lib/internal/engagements-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string; memberId: string }> };

/**
 * Phase 4 — engagement membership. DELETE removes a member from the engagement.
 */
export async function DELETE(_request: NextRequest, ctx: Ctx) {
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
  const { engagementId, memberId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  try {
    await cpRemoveEngagementMember(tid, engagementId, memberId);
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
