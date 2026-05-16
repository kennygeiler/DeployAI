import { decideSync } from "@deployai/authz";
import { type NextRequest, NextResponse } from "next/server";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";
import { cpPatchActionQueueItem } from "@/lib/internal/strategist-queues-cp";

/** Epic 9.5 — `POST /api/bff/action-queue/:id/progress` → `in_progress` (FR57). */
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
  const tid = actor.tenantId!.trim();
  try {
    const next = await cpPatchActionQueueItem(tid, id, {
      status: "in_progress",
      claimed_by: who,
    });
    return NextResponse.json({ item: next, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
