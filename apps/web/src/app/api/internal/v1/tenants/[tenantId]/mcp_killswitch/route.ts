import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpGetMcpKillSwitch, cpSetMcpKillSwitch } from "@/lib/internal/mcp-configs-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * v2 Phase 5 Wave 3H — outbound-MCP kill switch BFF (threat-model §5.5).
 * Proxies the Wave 3H CP route ``/internal/v1/tenants/{tid}/mcp_killswitch``.
 *
 * The actor id (JWT sub or dev header) is forwarded as
 * ``X-DeployAI-Actor-Id`` so the CP can stamp the ledger row with the
 * human who flipped the switch (incident response audit chain).
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
    const state = await cpGetMcpKillSwitch(g.tid);
    return NextResponse.json(state, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}

type WriteBody = { disabled?: unknown };

export async function POST(req: Request, ctx: { params: Promise<{ tenantId: string }> }) {
  const g = await guard(ctx.params);
  if ("error" in g) return g.error;
  let body: WriteBody;
  try {
    body = (await req.json()) as WriteBody;
  } catch {
    return new NextResponse("Bad Request: invalid JSON", { status: 400 });
  }
  if (typeof body.disabled !== "boolean") {
    return new NextResponse("Bad Request: disabled must be boolean", { status: 400 });
  }
  try {
    const state = await cpSetMcpKillSwitch(g.tid, body.disabled, await getActorIdFromHeaders());
    return NextResponse.json(state, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
