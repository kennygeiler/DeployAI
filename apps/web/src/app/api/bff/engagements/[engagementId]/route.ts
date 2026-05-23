import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpGetEngagement, cpListEngagementMembers } from "@/lib/internal/engagements-cp";
import {
  cpListMatrixEdges,
  cpListMatrixNodes,
  cpListMatrixProposals,
} from "@/lib/internal/matrix-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Engagement detail aggregate — one engagement with its team and deployment
 * matrix (nodes + edges), backing the /engagements/[engagementId] view. The
 * Phase 3 engagement-log was retired in increment 5.5 — the matrix supersedes
 * it.
 */
export async function GET(_request: NextRequest, ctx: Ctx) {
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
  const { engagementId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  try {
    const engagement = await cpGetEngagement(tid, engagementId);
    const [members, matrixNodes, matrixEdges, matrixProposals] = await Promise.all([
      cpListEngagementMembers(tid, engagementId),
      cpListMatrixNodes(tid, engagementId),
      cpListMatrixEdges(tid, engagementId),
      cpListMatrixProposals(tid, engagementId, "pending"),
    ]);
    return NextResponse.json(
      {
        engagement,
        members,
        matrix: {
          nodes: matrixNodes,
          edges: matrixEdges,
          proposals: matrixProposals,
        },
        source: "cp",
      },
      { status: 200 },
    );
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
