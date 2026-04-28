import { decideSync } from "@deployai/authz";
import { type NextRequest, NextResponse } from "next/server";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

/** Epic 10.7 — strategist personal audit feed from CP. */
export async function GET(request: NextRequest) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const tenantId = actor.tenantId?.trim();
  const actorId = await getActorIdFromHeaders();
  if (!tenantId || !actorId) {
    return NextResponse.json({ items: [], source: "unconfigured" }, { status: 200 });
  }
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return NextResponse.json({ items: [], source: "unconfigured" }, { status: 200 });
  }
  const category = request.nextUrl.searchParams.get("category")?.trim();
  const q = new URLSearchParams({ tenant_id: tenantId });
  if (category) {
    q.set("category", category);
  }
  const url = `${base}/internal/v1/strategist/personal-audit?${q.toString()}`;
  const r = await fetch(url, {
    method: "GET",
    headers: {
      "X-DeployAI-Internal-Key": key,
      "X-DeployAI-Actor-Id": actorId,
    },
    cache: "no-store",
  });
  if (!r.ok) {
    return NextResponse.json({ error: await r.text(), source: "cp" }, { status: r.status });
  }
  return NextResponse.json({ ...(await r.json()), source: "cp" }, { status: 200 });
}
