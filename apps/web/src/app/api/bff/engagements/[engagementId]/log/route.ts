import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpAddEngagementLogEntry, cpListEngagementLog } from "@/lib/internal/engagement-log-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

/**
 * Phase 3 — manual capture. GET lists / POST appends engagement log entries
 * (meeting / decision / risk / next-action notes).
 */
export async function GET(_request: NextRequest, ctx: Ctx) {
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
  try {
    const entries = await cpListEngagementLog(tid, engagementId);
    return NextResponse.json({ entries, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function POST(request: NextRequest, ctx: Ctx) {
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
  let parsed: { entry_kind?: unknown; body?: unknown };
  try {
    parsed = (await request.json()) as typeof parsed;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const entryKind = typeof parsed.entry_kind === "string" ? parsed.entry_kind : "";
  const text = typeof parsed.body === "string" ? parsed.body.trim() : "";
  if (!entryKind || !text) {
    return NextResponse.json({ error: "entry_kind and body are required" }, { status: 400 });
  }
  // Attribution is server-derived from the actor — not client-supplied — so a
  // log entry cannot be posted under someone else's name.
  const author = await getActorIdFromHeaders();
  try {
    const entry = await cpAddEngagementLogEntry(tid, engagementId, {
      entry_kind: entryKind,
      body: text,
      author,
    });
    return NextResponse.json({ entry, source: "cp" }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
