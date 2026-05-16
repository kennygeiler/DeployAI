import { decideSync } from "@deployai/authz";
import { type NextRequest, NextResponse } from "next/server";

import { mutateActionQueueItem, pushActionQueueAudit } from "@/lib/bff/strategist-queues-store";
import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueuesUseControlPlane } from "@/lib/internal/strategist-queues-backend";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";
import { cpPatchActionQueueItem } from "@/lib/internal/strategist-queues-cp";

/** Epic 9.5 — `POST /api/bff/action-queue/:id/claim` (FR56). */
export async function POST(_request: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) return cpMisconfigured;
  const { id } = await ctx.params;
  const who = actor.role === "deployment_strategist" ? "you" : actor.role;
  const tid = actor.tenantId?.trim();
  if (
    strategistQueuesUseControlPlane() &&
    tid &&
    getControlPlaneBaseUrl() &&
    getControlPlaneInternalKey()
  ) {
    try {
      const next = await cpPatchActionQueueItem(tid, id, { status: "claimed", claimed_by: who });
      return NextResponse.json({ item: next, source: "cp" }, { status: 200 });
    } catch (e) {
      return nextResponseFromStrategistCpFetchError(e);
    }
  }
  const next = mutateActionQueueItem(actor.tenantId ?? null, id, {
    status: "claimed",
    claimed_by: who,
  });
  if (!next) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  pushActionQueueAudit(actor.tenantId ?? null, "action_queue.claimed", {
    itemId: id,
    claimed_by: who,
  });
  return NextResponse.json({ item: next, source: "memory" }, { status: 200 });
}
