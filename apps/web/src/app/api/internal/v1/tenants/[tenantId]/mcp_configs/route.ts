import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import {
  CONNECTOR_KINDS,
  cpCreateMcpConfig,
  cpListMcpConfigs,
  type ConnectorKind,
} from "@/lib/internal/mcp-configs-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * v2 Phase 5 Wave 3H — outbound-MCP catalog BFF (list + create).
 *
 * Proxies ``/internal/v1/tenants/{tid}/mcp_configs`` on the control
 * plane. The tenant id in the URL must match the actor's tenant id;
 * cross-tenant access is RLS-protected on the CP side, but we reject it
 * up front here so the UI surfaces a clean 403 rather than relying on
 * the CP to return an empty list.
 *
 * The raw auth token may pass through this route (create body). It is
 * not logged here — body parsing happens after the guard, and the value
 * is forwarded verbatim to the CP which encrypts before persist.
 */

async function guard(params: Promise<{ tenantId: string }>) {
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
  const { tenantId } = await params;
  if (!tenantId || tenantId.trim() !== actor.tenantId!.trim()) {
    return { error: new NextResponse("Forbidden", { status: 403 }) } as const;
  }
  return { tid: tenantId.trim() } as const;
}

export async function GET(_req: Request, ctx: { params: Promise<{ tenantId: string }> }) {
  const g = await guard(ctx.params);
  if ("error" in g) return g.error;
  try {
    const configs = await cpListMcpConfigs(g.tid);
    return NextResponse.json({ configs }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

type CreateBody = {
  name?: unknown;
  connector_kind?: unknown;
  endpoint?: unknown;
  transport?: unknown;
  auth_token?: unknown;
  allowed_tools?: unknown;
  enabled?: unknown;
};

export async function POST(req: Request, ctx: { params: Promise<{ tenantId: string }> }) {
  const g = await guard(ctx.params);
  if ("error" in g) return g.error;
  let body: CreateBody;
  try {
    body = (await req.json()) as CreateBody;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  if (typeof body.name !== "string" || !body.name.trim()) {
    return new NextResponse("Bad Request: name is required", { status: 400 });
  }
  if (
    typeof body.connector_kind !== "string" ||
    !(CONNECTOR_KINDS as readonly string[]).includes(body.connector_kind)
  ) {
    return new NextResponse(
      `Bad Request: connector_kind must be one of ${CONNECTOR_KINDS.join(", ")}`,
      { status: 400 },
    );
  }
  if (typeof body.endpoint !== "string" || !body.endpoint.trim()) {
    return new NextResponse("Bad Request: endpoint is required", { status: 400 });
  }
  try {
    const config = await cpCreateMcpConfig(
      g.tid,
      {
        name: body.name.trim(),
        connector_kind: body.connector_kind as ConnectorKind,
        endpoint: body.endpoint.trim(),
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
    return NextResponse.json({ config }, { status: 201 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
