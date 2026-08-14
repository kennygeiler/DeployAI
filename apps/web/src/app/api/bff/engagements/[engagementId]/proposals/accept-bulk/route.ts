import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpBulkAcceptMatrixProposals } from "@/lib/internal/matrix-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Bulk-accept matrix proposals from the Brief's Needs-you queue — the BFF
 * sibling of the single accept/reject routes and the demo-callable surface
 * behind the "Accept all pending" button (the guided tour's Monday-gate and
 * Friday-digest beats direct guests to it, and demo_guest cannot reach the
 * `/api/internal/v1` proxy).
 *
 * Gated with `canonical:read` — deliberately the same posture as the single
 * proposal accept/reject BFF routes, and the same accepted residual risk for
 * demo sessions (see the demo_session_internal.py security notes: the demo
 * tenant is disposable and isolated by tenancy). Proxies the CP
 * `/proposals/accept-bulk` endpoint: nodes before edges, per-row
 * transactions, partial-success counts, 500-row cap.
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
