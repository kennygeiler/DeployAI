import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { canRegenerateIntakeAddress } from "@/lib/internal/intake-address-authz";
import { cpRegenerateIntakeAddress } from "@/lib/internal/intake-address-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Wave 5 IN2 — rotate the engagement's intake address (revokes the old one).
 *
 * Admin-only: mail sent to the old address silently drops after rotation,
 * so this is a destructive control — customer_admin / platform_admin, gated
 * here because the CP internal route trusts its caller (see
 * `intake-address-authz.ts` for why this is a role check, not `decideSync`
 * against a matrix action).
 */
export async function POST(_request: NextRequest, ctx: Ctx) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", {
    kind: "canonical_memory",
    tenantId: actor.tenantId,
  });
  if (!d.allow || !canRegenerateIntakeAddress(actor.role)) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return cpMisconfigured;
  }
  const { engagementId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  try {
    const actorId = await getActorIdFromHeaders();
    const address = await cpRegenerateIntakeAddress(tid, engagementId, actorId);
    return NextResponse.json({ ...address, can_regenerate: true }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
