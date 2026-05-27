import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpFinishMcpOAuth } from "@/lib/internal/mcp-configs-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * v2 Phase 5 Wave 3H — Slack OAuth callback BFF.
 * Proxies ``/internal/v1/tenants/{tid}/mcp_configs/{cid}/oauth/callback``.
 * Body: ``{code, state}``. Returns the updated TenantMcpConfigRead.
 */

async function guard(params: Promise<{ tenantId: string; configId: string }>) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return { error: new NextResponse("Unauthorized", { status: 401 }) } as const;
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return { error: new NextResponse("Forbidden", { status: 403 }) } as const;
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) {
    return { error: cpMisconfigured } as const;
  }
  const { tenantId, configId } = await params;
  if (!tenantId || tenantId.trim() !== actor.tenantId!.trim()) {
    return { error: new NextResponse("Forbidden", { status: 403 }) } as const;
  }
  if (!configId || !configId.trim()) {
    return { error: new NextResponse("Bad Request: configId required", { status: 400 }) } as const;
  }
  return { tid: tenantId.trim(), cid: configId.trim() } as const;
}

type CallbackBody = { code?: unknown; state?: unknown };

export async function POST(
  req: Request,
  ctx: { params: Promise<{ tenantId: string; configId: string }> },
) {
  const g = await guard(ctx.params);
  if ("error" in g) return g.error;
  let body: CallbackBody;
  try {
    body = (await req.json()) as CallbackBody;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  if (typeof body.code !== "string" || !body.code.trim()) {
    return new NextResponse("Bad Request: code required", { status: 400 });
  }
  if (typeof body.state !== "string" || !body.state.trim()) {
    return new NextResponse("Bad Request: state required", { status: 400 });
  }
  try {
    const config = await cpFinishMcpOAuth(
      g.tid,
      g.cid,
      body.code.trim(),
      body.state.trim(),
      await getActorIdFromHeaders(),
    );
    return NextResponse.json({ config }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
