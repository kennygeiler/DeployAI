import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpListTenantInsights } from "@/lib/internal/insights-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Phase 7 (increment 7.4) — list portfolio (tenant-scoped, Master
 * Strategist) insights. The actor's tenant id scopes the query; no
 * tenant id in the path so the client cannot list someone else's
 * portfolio by URL fiddling.
 */
export async function GET(request: NextRequest) {
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
  const tid = actor.tenantId!.trim();
  const statusParam = request.nextUrl.searchParams.get("status");
  const allowed = ["open", "dismissed", "resolved"] as const;
  const status: (typeof allowed)[number] | null =
    statusParam && (allowed as readonly string[]).includes(statusParam)
      ? (statusParam as (typeof allowed)[number])
      : statusParam === null
        ? "open"
        : null;
  if (status === null) {
    return NextResponse.json({ error: "invalid status" }, { status: 400 });
  }
  try {
    const insights = await cpListTenantInsights(tid, status);
    return NextResponse.json({ insights, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
