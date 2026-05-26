import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

type Ctx = { params: Promise<{ engagementId: string; nodeId: string }> };

/**
 * G2.c — PATCH a matrix node. Forwards a sparse body (only mutable fields)
 * to the existing CP `update_matrix_node` route which dual-emits
 * `matrix_node_updated`.
 */
export async function PATCH(request: NextRequest, ctx: Ctx) {
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
  const { engagementId, nodeId } = await ctx.params;
  const tid = actor.tenantId!.trim();

  let parsed: { title?: unknown; node_type?: unknown; attributes?: unknown };
  try {
    parsed = (await request.json()) as typeof parsed;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const body: Record<string, unknown> = {};
  if (typeof parsed.title === "string" && parsed.title.trim().length > 0) {
    body.title = parsed.title.trim();
  }
  if (typeof parsed.node_type === "string" && parsed.node_type.trim().length > 0) {
    body.node_type = parsed.node_type.trim();
  }
  if (
    parsed.attributes !== undefined &&
    parsed.attributes !== null &&
    typeof parsed.attributes === "object" &&
    !Array.isArray(parsed.attributes)
  ) {
    body.attributes = parsed.attributes;
  }
  if (Object.keys(body).length === 0) {
    return NextResponse.json({ error: "no editable fields supplied" }, { status: 400 });
  }

  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return NextResponse.json({ error: "control-plane misconfigured" }, { status: 503 });
  }
  const url =
    `${base}/internal/v1/engagements/${encodeURIComponent(engagementId)}` +
    `/matrix/nodes/${encodeURIComponent(nodeId)}` +
    `?tenant_id=${encodeURIComponent(tid)}`;
  try {
    const r = await fetch(url, {
      method: "PATCH",
      headers: { "X-DeployAI-Internal-Key": key, "Content-Type": "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
    });
    if (!r.ok) {
      const text = await r.text();
      return NextResponse.json({ error: text || `cp ${r.status}` }, { status: r.status });
    }
    const node: unknown = await r.json();
    return NextResponse.json({ node, source: "cp" }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
