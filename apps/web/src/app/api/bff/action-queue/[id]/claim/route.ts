import { decideSync } from "@deployai/authz";
import { type NextRequest, NextResponse } from "next/server";

import { mutateActionQueueItem, pushActionQueueAudit } from "@/lib/bff/strategist-queues-store";
import { getActorFromHeaders } from "@/lib/internal/actor";

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
  const { id } = await ctx.params;
  const who = actor.role === "deployment_strategist" ? "you" : actor.role;
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
  return NextResponse.json({ item: next }, { status: 200 });
}
