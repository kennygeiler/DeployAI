import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpListTimeline } from "@/lib/internal/engagement-timeline-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

const DEFAULT_DAYS = 180;
const MAX_DAYS = 365;

/**
 * Engagement timeline — chronological view of canonical_memory_events for
 * one engagement. Backs the EngagementTimeline card on the engagement
 * detail page. Defaults to the last 180 days; `?days=N` clamps to 1..365.
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
  const tid = actor.tenantId!.trim();
  const raw = request.nextUrl.searchParams.get("days");
  let days = DEFAULT_DAYS;
  if (raw !== null) {
    const parsed = Number(raw);
    if (!Number.isFinite(parsed) || !Number.isInteger(parsed) || parsed < 1 || parsed > MAX_DAYS) {
      return NextResponse.json({ error: "invalid days" }, { status: 400 });
    }
    days = parsed;
  }
  try {
    const body = await cpListTimeline(tid, engagementId, days);
    return NextResponse.json({ ...body, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
