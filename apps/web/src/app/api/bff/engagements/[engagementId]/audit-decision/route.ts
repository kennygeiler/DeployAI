import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string }> };

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * G2.c — soft-reject an AI-produced proposal via the ledger event id that
 * recorded its creation. Forwards to CP `/audit-decision`; CP enforces the
 * tenant scope on the event lookup.
 */
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

  let parsed: { event_id?: unknown; reason?: unknown };
  try {
    parsed = (await request.json()) as typeof parsed;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const eventId = typeof parsed.event_id === "string" ? parsed.event_id.trim() : "";
  if (!eventId || !UUID_RE.test(eventId)) {
    return NextResponse.json({ error: "event_id must be a uuid" }, { status: 400 });
  }
  const reason =
    typeof parsed.reason === "string" && parsed.reason.trim().length > 0
      ? parsed.reason.trim().slice(0, 2000)
      : null;

  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return NextResponse.json({ error: "control-plane misconfigured" }, { status: 503 });
  }
  const url =
    `${base}/internal/v1/engagements/${encodeURIComponent(engagementId)}/audit-decision` +
    `?tenant_id=${encodeURIComponent(tid)}`;
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: { "X-DeployAI-Internal-Key": key, "Content-Type": "application/json" },
      body: JSON.stringify({ event_id: eventId, reason }),
      cache: "no-store",
    });
    if (!r.ok) {
      const text = await r.text();
      return NextResponse.json({ error: text || `cp ${r.status}` }, { status: r.status });
    }
    const proposal: unknown = await r.json();
    return NextResponse.json({ proposal, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
