import { NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { cpListMcpAudit } from "@/lib/internal/mcp-audit-cp";
import { nextResponseFromStrategistCpFetchError } from "@/lib/internal/strategist-bff-cp-error";
import { strategistQueueBffCpMisconfiguredResponse } from "@/lib/internal/strategist-queues-route-guard";

/**
 * Wave 3I — admin BFF for the tenant-wide outbound-MCP audit slice.
 *
 * Proxies ``GET /internal/v1/tenants/{tenant_id}/mcp_audit`` with the
 * strategist actor's tenant id from the JWT / dev header. The CP route
 * pins the source_kind set to the MCP slice on its end too (defense in
 * depth) so this BFF stays a thin transport.
 */

const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;

export async function GET(req: Request) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const cpMisconfigured = strategistQueueBffCpMisconfiguredResponse(actor.tenantId);
  if (cpMisconfigured) return cpMisconfigured;

  const url = new URL(req.url);
  const limitRaw = url.searchParams.get("limit");
  let limit = DEFAULT_LIMIT;
  if (limitRaw !== null) {
    const n = Number.parseInt(limitRaw, 10);
    if (!Number.isFinite(n) || n < 1 || n > MAX_LIMIT) {
      return new NextResponse(`Bad Request: limit must be 1..${MAX_LIMIT}`, { status: 400 });
    }
    limit = n;
  }

  try {
    const rows = await cpListMcpAudit(actor.tenantId!.trim(), { limit });
    return NextResponse.json({ rows }, { status: 200 });
  } catch (e) {
    return nextResponseFromStrategistCpFetchError(e);
  }
}
