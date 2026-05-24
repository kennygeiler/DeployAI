import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpGetEventsByIds } from "@/lib/internal/events-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

const MAX_IDS = 50;
const UUID_RE = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;

/**
 * Citation drill-down — return the canonical_memory_events behind a node's
 * evidence_event_ids or an insight's citation_event_ids. `?ids=a,b,c`,
 * deduped + capped at 50. Backs the CitationPanel on the engagement detail
 * page.
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
  const raw = request.nextUrl.searchParams.get("ids") ?? "";
  const seen = new Set<string>();
  const ids: string[] = [];
  for (const chunk of raw.split(",")) {
    const s = chunk.trim();
    if (!s || seen.has(s)) {
      continue;
    }
    if (!UUID_RE.test(s)) {
      return NextResponse.json({ error: `invalid id: ${s}` }, { status: 400 });
    }
    seen.add(s);
    ids.push(s);
  }
  if (ids.length === 0) {
    return NextResponse.json({ events: [], source: "cp" }, { status: 200 });
  }
  if (ids.length > MAX_IDS) {
    return NextResponse.json(
      { error: `too many ids: ${ids.length} (max ${MAX_IDS})` },
      { status: 400 },
    );
  }
  try {
    const body = await cpGetEventsByIds(tid, engagementId, ids);
    return NextResponse.json({ ...body, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
