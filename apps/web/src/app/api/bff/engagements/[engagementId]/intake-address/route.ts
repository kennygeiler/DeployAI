import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { canRegenerateIntakeAddress } from "@/lib/internal/intake-address-authz";
import { cpGetIntakeAddress } from "@/lib/internal/intake-address-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Wave 5 IN2 — the engagement's inbound-email intake address.
 *
 * Proxies CP `GET /internal/v1/engagements/{id}/intake-address` (the CP
 * mints the address lazily on first read). Gate: `canonical:read`, same as
 * the Capture surface that renders it. The response adds `can_regenerate`
 * so the client can hide the admin-only Regenerate control instead of
 * offering a button that would 403.
 */
export async function GET(_request: NextRequest, ctx: Ctx) {
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
  try {
    const address = await cpGetIntakeAddress(tid, engagementId);
    return NextResponse.json(
      { ...address, can_regenerate: canRegenerateIntakeAddress(actor.role) },
      { status: 200 },
    );
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
