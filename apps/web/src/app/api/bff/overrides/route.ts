import { decideSync } from "@deployai/authz";
import { type NextRequest, NextResponse } from "next/server";

import { getActorFromHeaders, getActorIdFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

type OverrideListItem = {
  override_event_id: string;
  occurred_at: string;
  learning_id: string;
  learning_belief: string;
  reason: string;
  overriding_evidence_count: number;
  overriding_evidence_event_ids: string[];
  author_actor_id: string;
};

/** Epic 10.2 / 10.6 — proxy to CP internal strategist overrides API. */
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
  const sp = request.nextUrl.searchParams;
  const mineOnly = sp.get("mineOnly") === "1" || sp.get("mine_only") === "1";
  const from = sp.get("from")?.trim();
  const to = sp.get("to")?.trim();
  const q = new URLSearchParams({ tenant_id: tenantId });
  if (mineOnly) {
    q.set("mine_only", "true");
  }
  if (from) {
    q.set("from", from);
  }
  if (to) {
    q.set("to", to);
  }
  const url = `${base}/internal/v1/strategist/overrides?${q.toString()}`;
  const headers: Record<string, string> = {
    "X-DeployAI-Internal-Key": key,
    "X-DeployAI-Actor-Id": actorId,
  };
  const r = await fetch(url, { method: "GET", headers, cache: "no-store" });
  if (!r.ok) {
    return NextResponse.json({ error: await r.text(), source: "cp" }, { status: r.status });
  }
  const data = (await r.json()) as { items: OverrideListItem[] };
  return NextResponse.json({ ...data, source: "cp" }, { status: 200 });
}

export async function POST(request: NextRequest) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "override:submit", { kind: "canonical_memory" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const tenantId = actor.tenantId?.trim();
  const actorId = await getActorIdFromHeaders();
  if (!tenantId || !actorId) {
    return NextResponse.json({ error: "tenant or actor not configured" }, { status: 400 });
  }
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return NextResponse.json({ error: "control plane not configured" }, { status: 503 });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (typeof body !== "object" || body === null) {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }
  const url = `${base}/internal/v1/strategist/overrides?tenant_id=${encodeURIComponent(tenantId)}`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-DeployAI-Internal-Key": key,
      "X-DeployAI-Actor-Id": actorId,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const text = await r.text();
  return new NextResponse(text, {
    status: r.status,
    headers: { "content-type": r.headers.get("content-type") ?? "application/json" },
  });
}
