import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpResolveReviewItem } from "@/lib/internal/review-inbox-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ itemId: string }> };

/**
 * Pilot-refresh E1/E2 — resolve one review item. For agent escalations an
 * `answer_text` (plus optional `answer_citations`) records the canonical
 * `human_escalation_answer` ledger event on the control plane — the
 * knowledge-flywheel write path. The resolver's id comes from the
 * server-side actor, never from the client body.
 */

const BodySchema = z.object({
  resolution_note: z.string().max(2000).nullable().optional(),
  answer_text: z.string().max(8000).nullable().optional(),
  answer_citations: z.array(z.string().max(200)).max(50).optional(),
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

  let body: z.infer<typeof BodySchema>;
  try {
    body = BodySchema.parse((await request.json()) as unknown);
  } catch (e) {
    return NextResponse.json(
      {
        error: "bad_request",
        code: "bff_validation_failed",
        userMessage: "The resolve request was malformed.",
        detail: e instanceof Error ? e.message.slice(0, 500) : undefined,
      },
      { status: 400 },
    );
  }

  try {
    const item = await cpResolveReviewItem(tid, itemId, {
      resolved_by: actorId,
      resolution_note: body.resolution_note ?? null,
      answer_text: body.answer_text ?? null,
      answer_citations: body.answer_citations ?? [],
    });
    return NextResponse.json({ item, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
