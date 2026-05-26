import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { cpRevokeTenantApiKey } from "@/lib/internal/api-keys-cp";
import { emitTenantAuditEventBackground } from "@/lib/internal/audit-emit";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

async function guard() {
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
  return { tid: actor.tenantId!.trim() } as const;
}

export async function DELETE(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const g = await guard();
  if ("error" in g) return g.error;
  const { id } = await ctx.params;
  if (!id || !id.trim()) {
    return new NextResponse("Bad Request: id is required", { status: 400 });
  }
  try {
    await cpRevokeTenantApiKey(g.tid, id);
    emitTenantAuditEventBackground(
      g.tid,
      await getActorIdFromHeaders(),
      "tenant.api_key.revoked",
      `revoked MCP api key ${id}`,
      { api_key_id: id },
      id,
    );
    return new NextResponse(null, { status: 204 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
