import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import {
  getActorFromHeaders,
  getActorIdFromHeaders,
  getDemoSessionJtiFromHeaders,
} from "@/lib/internal/actor";
import { cpGetOracleHistory } from "@/lib/internal/oracle-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

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
  const actorId = await getActorIdFromHeaders();
  if (!actorId) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const { engagementId } = await ctx.params;
  const tid = actor.tenantId!.trim();
  // demo-polish fix 5 — a demo guest's history is its own session's thread,
  // never previous visitors' turns on the shared demo user.
  const demoJti = actor.role === "demo_guest" ? await getDemoSessionJtiFromHeaders() : null;
  try {
    const history = await cpGetOracleHistory(tid, engagementId, actorId, demoJti);
    return NextResponse.json({ ...history, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
