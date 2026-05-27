import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpDeleteMcpConfig, cpGetMcpConfig, cpPatchMcpConfig } from "@/lib/internal/mcp-configs-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * v2 Phase 5 Wave 3H — per-config BFF (get / patch / delete).
 * Proxies ``/internal/v1/tenants/{tid}/mcp_configs/{cid}`` on the CP.
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

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ tenantId: string; configId: string }> },
) {
  const g = await guard(ctx.params);
  if ("error" in g) return g.error;
  try {
    const config = await cpGetMcpConfig(g.tid, g.cid);
    return NextResponse.json({ config }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

type PatchBody = {
  name?: unknown;
  endpoint?: unknown;
  transport?: unknown;
  auth_token?: unknown;
  allowed_tools?: unknown;
  enabled?: unknown;
};

export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ tenantId: string; configId: string }> },
) {
  const g = await guard(ctx.params);
  if ("error" in g) return g.error;
  let body: PatchBody;
  try {
    body = (await req.json()) as PatchBody;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  try {
    const config = await cpPatchMcpConfig(
      g.tid,
      g.cid,
      {
        ...(typeof body.name === "string" && body.name.trim() ? { name: body.name.trim() } : {}),
        ...(typeof body.endpoint === "string" && body.endpoint.trim()
          ? { endpoint: body.endpoint.trim() }
          : {}),
        ...(typeof body.transport === "string" && body.transport === "http_sse"
          ? { transport: "http_sse" as const }
          : {}),
        ...(typeof body.auth_token === "string" && body.auth_token.length > 0
          ? { auth_token: body.auth_token }
          : {}),
        ...(Array.isArray(body.allowed_tools)
          ? { allowed_tools: body.allowed_tools.filter((t): t is string => typeof t === "string") }
          : body.allowed_tools === null
            ? { allowed_tools: null }
            : {}),
        ...(typeof body.enabled === "boolean" ? { enabled: body.enabled } : {}),
      },
      await getActorIdFromHeaders(),
    );
    return NextResponse.json({ config }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ tenantId: string; configId: string }> },
) {
  const g = await guard(ctx.params);
  if ("error" in g) return g.error;
  try {
    await cpDeleteMcpConfig(g.tid, g.cid, await getActorIdFromHeaders());
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
