import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpFileCitationDispute } from "@/lib/internal/review-inbox-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Pilot-refresh E3 — flag a wrong citation. Creates a
 * review_item(kind=citation_dispute) + ledger event on the control plane;
 * the Review Inbox resolves it and the Part 4 eval loop consumes it.
 */

const BodySchema = z.object({
  turn_id: z.string().max(200).nullable().optional(),
  citation_id: z.string().min(1).max(200),
  reason: z.string().min(1).max(2000),
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
  const { engagementId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  const actorId = await getActorIdFromHeaders();

  let body: z.infer<typeof BodySchema>;
  try {
    body = BodySchema.parse((await request.json()) as unknown);
  } catch (e) {
    return NextResponse.json(
      {
        error: "bad_request",
        code: "bff_validation_failed",
        userMessage: "The citation dispute was malformed.",
        detail: e instanceof Error ? e.message.slice(0, 500) : undefined,
      },
      { status: 400 },
    );
  }

  try {
    const item = await cpFileCitationDispute(tid, {
      engagement_id: engagementId,
      turn_id: body.turn_id ?? null,
      citation_id: body.citation_id,
      reason: body.reason,
      created_by: actorId,
    });
    return NextResponse.json({ item, source: "cp" }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
