import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpAcceptMatrixProposal } from "@/lib/internal/matrix-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string; proposalId: string }> };

/**
 * Phase 6 (increment 6.2a) — accept a matrix proposal: commits the
 * proposed node or edge into the matrix with `evidence_event_ids =
 * [source_event_id]`. The acting user's id is taken from the server-side
 * actor, not the client, so acceptance attribution is trustworthy.
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
  const { engagementId, proposalId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  const actorId = await getActorIdFromHeaders();
  try {
    const proposal = await cpAcceptMatrixProposal(tid, engagementId, proposalId, {
      actor_id: actorId,
    });
    return NextResponse.json({ proposal, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
