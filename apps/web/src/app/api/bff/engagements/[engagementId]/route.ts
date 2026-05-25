import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpGetEngagementDetail } from "@/lib/internal/engagements-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Engagement detail aggregate — one engagement with its team and deployment
 * matrix (nodes + edges), backing the /engagements/[engagementId] view. The
 * Phase 3 engagement-log was retired in increment 5.5 — the matrix supersedes
 * it. Phase D D3.a collapsed the six sequential CP calls this route used to
 * fan out into a single aggregate endpoint; see
 * `docs/perf/engagement-aggregate-query-budget.md`.
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
    const detail = await cpGetEngagementDetail(tid, engagementId);
    return NextResponse.json(
      {
        engagement: detail.engagement,
        members: detail.members,
        matrix: {
          nodes: detail.matrix_nodes,
          edges: detail.matrix_edges,
          proposals: detail.matrix_proposals,
          node_types: detail.custom_node_types,
        },
        source: "cp",
      },
      { status: 200 },
    );
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
