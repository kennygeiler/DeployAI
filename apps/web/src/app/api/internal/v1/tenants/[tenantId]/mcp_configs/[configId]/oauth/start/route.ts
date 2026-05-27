import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpStartMcpOAuth } from "@/lib/internal/mcp-configs-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * v2 Phase 5 Wave 3H — Slack OAuth start BFF.
 * Proxies ``/internal/v1/tenants/{tid}/mcp_configs/{cid}/oauth/start``.
 * Body: ``{redirect_uri}``. Response: ``{authorization_url, state}``.
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

type StartBody = { redirect_uri?: unknown };

export async function POST(
  req: Request,
  ctx: { params: Promise<{ tenantId: string; configId: string }> },
) {
  const g = await guard(ctx.params);
  if ("error" in g) return g.error;
  let body: StartBody;
  try {
    body = (await req.json()) as StartBody;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  if (typeof body.redirect_uri !== "string" || !body.redirect_uri.trim()) {
    return new NextResponse("Bad Request: redirect_uri required", { status: 400 });
  }
  try {
    const result = await cpStartMcpOAuth(
      g.tid,
      g.cid,
      body.redirect_uri.trim(),
      await getActorIdFromHeaders(),
    );
    return NextResponse.json(result, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
