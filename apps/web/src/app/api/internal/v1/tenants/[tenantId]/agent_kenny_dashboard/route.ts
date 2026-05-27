import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import {
  cpGetAgentKennyDashboard,
  WINDOW_DAYS_MAX,
  WINDOW_DAYS_MIN,
} from "@/lib/internal/agent-kenny-dashboard-cp";
import { getActorFromHeaders } from "@/lib/internal/actor";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Phase 6 Wave C — BFF proxy for the Agent Kenny telemetry dashboard.
 *
 * Mirrors the Wave 3I MCP-audit BFF shape: actor → authz → CP env check
 * → tenant-id guard → forward to the CP route. The CP does the
 * aggregation; this is a transparent transport that validates the
 * tenant-id path param against the actor's JWT tenant so a strategist
 * cannot read another tenant's telemetry by URL fiddling.
 */
export async function GET(_req: Request, ctx: { params: Promise<{ tenantId: string }> }) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) return cpMisconfigured;

  const { tenantId } = await ctx.params;
  if (!tenantId || tenantId.trim() !== actor.tenantId!.trim()) {
    return new NextResponse("Forbidden", { status: 403 });
  }

  const url = new URL(_req.url);
  const windowRaw = url.searchParams.get("window_days");
  let windowDays: number | undefined;
  if (windowRaw !== null) {
    const n = Number.parseInt(windowRaw, 10);
    if (!Number.isFinite(n) || n < WINDOW_DAYS_MIN || n > WINDOW_DAYS_MAX) {
      return new NextResponse(
        `Bad Request: window_days must be ${WINDOW_DAYS_MIN}..${WINDOW_DAYS_MAX}`,
        { status: 400 },
      );
    }
    windowDays = n;
  }

  try {
    const dashboard = await cpGetAgentKennyDashboard(tenantId.trim(), { windowDays });
    return NextResponse.json(dashboard, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
