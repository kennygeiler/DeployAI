import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { AT_DATE_PATTERN, cpGetMatrixSnapshot } from "@/lib/internal/matrix-snapshot-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Phase F3.c — historical matrix snapshot proxy. Forwards `at=YYYY-MM-DD`
 * to the CP F3.b endpoint after Zod-validating the format. 404 means no
 * snapshot exists at/before that date for the engagement.
 */
export async function GET(request: NextRequest, ctx: Ctx) {
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
  const at = new URL(request.url).searchParams.get("at");
  if (!at || !AT_DATE_PATTERN.test(at)) {
    return NextResponse.json(
      { error: "at must match YYYY-MM-DD", code: "invalid_at" },
      { status: 422 },
    );
  }
  const tid = actor.tenantId!.trim();
  try {
    const snapshot = await cpGetMatrixSnapshot(tid, engagementId, at);
    return NextResponse.json({ snapshot, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
