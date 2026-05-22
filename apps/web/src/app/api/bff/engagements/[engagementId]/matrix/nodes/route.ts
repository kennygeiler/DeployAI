import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpCreateMatrixNode } from "@/lib/internal/matrix-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Phase 5 — structured capture. POST creates a matrix node (a typed
 * entity — stakeholder / system / decision / risk / …) on the engagement.
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
  let parsed: { node_type?: unknown; title?: unknown; status?: unknown };
  try {
    parsed = (await request.json()) as typeof parsed;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const nodeType = typeof parsed.node_type === "string" ? parsed.node_type : "";
  const title = typeof parsed.title === "string" ? parsed.title.trim() : "";
  if (!nodeType || !title) {
    return NextResponse.json({ error: "node_type and title are required" }, { status: 400 });
  }
  const status =
    typeof parsed.status === "string" && parsed.status.trim() ? parsed.status.trim() : null;
  try {
    const node = await cpCreateMatrixNode(tid, engagementId, {
      node_type: nodeType,
      title,
      status,
    });
    return NextResponse.json({ node, source: "cp" }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
