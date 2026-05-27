import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpBulkAcceptMatrixProposals } from "@/lib/internal/matrix-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Bulk-accept matrix proposals — proxies to the CP `/proposals/accept-bulk`
 * route. The CP wraps the existing single-accept code path per row, orders
 * node proposals before edges (so an edge that references a node in the
 * same batch lands after its target), and reports partial-success counts.
 *
 * Caller may pass either an explicit `proposal_ids` list or a `filter`
 * block (status / proposal_kind), not both. The actor id is taken from
 * the server-side actor, not the client body, so attribution stays
 * trustworthy.
 */

const RequestBodySchema = z
  .object({
    proposal_ids: z.array(z.string().uuid()).max(500).optional(),
    filter: z
      .object({
        status: z.string().max(50).nullable().optional(),
        proposal_kind: z.string().max(50).nullable().optional(),
      })
      .optional(),
  })
  .refine(
    (b) => (b.proposal_ids === undefined) !== (b.filter === undefined),
    "Provide exactly one of proposal_ids or filter",
  );

const ResponseSchema = z.object({
  accepted: z.number().int().nonnegative(),
  failed: z.array(z.object({ id: z.string(), error: z.string() })),
  skipped: z.number().int().nonnegative(),
});

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
  const actorId = await getActorIdFromHeaders();

  let parsedBody: z.infer<typeof RequestBodySchema>;
  try {
    const raw = (await request.json()) as unknown;
    parsedBody = RequestBodySchema.parse(raw);
  } catch (e) {
    return NextResponse.json(
      {
        error: "bad_request",
        code: "bff_validation_failed",
        userMessage: "The bulk-accept request was malformed.",
        detail: e instanceof Error ? e.message.slice(0, 500) : undefined,
      },
      { status: 400 },
    );
  }

  try {
    const cpBody = parsedBody.proposal_ids
      ? { proposal_ids: parsedBody.proposal_ids, actor_id: actorId }
      : { filter: parsedBody.filter!, actor_id: actorId };
    const result = await cpBulkAcceptMatrixProposals(tid, engagementId, cpBody);
    const validated = ResponseSchema.parse(result);
    return NextResponse.json(validated, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
