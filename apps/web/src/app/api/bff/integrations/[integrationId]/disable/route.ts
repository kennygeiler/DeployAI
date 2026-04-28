import { cookies } from "next/headers";
import { type NextRequest, NextResponse } from "next/server";

import { decideSync } from "@deployai/authz";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";
import { accessTokenCookieNameFromEnv } from "@/lib/internal/deployai-access-jwt";

export async function POST(
  _request: NextRequest,
  ctx: { params: Promise<{ integrationId: string }> },
) {
  const actor = await getActorFromHeaders();
  if (!actor?.tenantId?.trim()) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "integration:kill_switch", {
    kind: "tenant",
    id: actor.tenantId,
  });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const { integrationId } = await ctx.params;
  const c = await cookies();
  const token = c.get(accessTokenCookieNameFromEnv())?.value;
  if (!token?.trim()) {
    return new NextResponse("Unauthorized: missing access token cookie", { status: 401 });
  }
  const base = getControlPlaneBaseUrl();
  if (!base) {
    return new NextResponse("Service unavailable", { status: 503 });
  }
  const url = `${base.replace(/\/$/, "")}/integrations/${encodeURIComponent(integrationId)}/disable`;
  const r = await fetch(url, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = await r.text();
  return new NextResponse(body || null, {
    status: r.status,
    headers: { "Content-Type": r.headers.get("Content-Type") ?? "application/json" },
  });
}
