import { NextResponse } from "next/server";
import { z } from "zod";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpReviewItemCounts } from "@/lib/internal/review-inbox-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Pilot-refresh E1 — open review-item counts for the StrategistNav badge.
 * Extraction proposals are engagement-scoped and not included here; the
 * badge covers the stored review_items kinds.
 */

const CountsSchema = z.object({
  open: z.number().int().nonnegative(),
  agent_escalation: z.number().int().nonnegative(),
  citation_dispute: z.number().int().nonnegative(),
  commitment_confirmation: z.number().int().nonnegative(),
});

export async function GET() {
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
  try {
    const counts = CountsSchema.parse(await cpReviewItemCounts(actor.tenantId!.trim()));
    return NextResponse.json({ counts, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
