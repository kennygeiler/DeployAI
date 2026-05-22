import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpCreateMatrixEdge } from "@/lib/internal/matrix-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Phase 5 — structured capture. POST creates a typed matrix edge (a
 * relationship) between two nodes on the engagement.
 */
export async function POST(request: NextRequest, ctx: Ctx) {
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
  let parsed: { edge_type?: unknown; from_node_id?: unknown; to_node_id?: unknown };
  try {
    parsed = (await request.json()) as typeof parsed;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const edgeType = typeof parsed.edge_type === "string" ? parsed.edge_type : "";
  const fromNodeId = typeof parsed.from_node_id === "string" ? parsed.from_node_id : "";
  const toNodeId = typeof parsed.to_node_id === "string" ? parsed.to_node_id : "";
  if (!edgeType || !fromNodeId || !toNodeId) {
    return NextResponse.json(
      { error: "edge_type, from_node_id and to_node_id are required" },
      { status: 400 },
    );
  }
  try {
    const edge = await cpCreateMatrixEdge(tid, engagementId, {
      edge_type: edgeType,
      from_node_id: fromNodeId,
      to_node_id: toNodeId,
    });
    return NextResponse.json({ edge, source: "cp" }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
