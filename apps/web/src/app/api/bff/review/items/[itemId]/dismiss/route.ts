import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpDismissReviewItem } from "@/lib/internal/review-inbox-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ itemId: string }> };

/** Pilot-refresh E1 — dismiss one review item (no action taken). */

const BodySchema = z.object({
  resolution_note: z.string().max(2000).nullable().optional(),
});

export async function POST(request: NextRequest, ctx: Ctx) {
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
  const { itemId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  const actorId = await getActorIdFromHeaders();

  let body: z.infer<typeof BodySchema> = {};
  try {
    body = BodySchema.parse((await request.json()) as unknown);
  } catch {
    // An empty / missing body is fine for dismiss.
    body = {};
  }

  try {
    const item = await cpDismissReviewItem(tid, itemId, {
      resolved_by: actorId,
      resolution_note: body.resolution_note ?? null,
    });
    return NextResponse.json({ item, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
