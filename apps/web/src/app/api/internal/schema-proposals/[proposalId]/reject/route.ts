import { decideSync } from "@deployai/authz";
import { type NextRequest, NextResponse } from "next/server";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export async function POST(request: NextRequest, ctx: { params: Promise<{ proposalId: string }> }) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "admin:promote_schema", { kind: "schema_proposals" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const { proposalId } = await ctx.params;
  const q = request.nextUrl.searchParams;
  const tenant = q.get("tenant")?.trim() ?? "";
  if (!tenant) {
    return NextResponse.json({ error: "Query ?tenant=<uuid> is required" }, { status: 400 });
  }
  const body = (await request.json().catch(() => ({}))) as { rejection_reason?: string };
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return NextResponse.json({ error: "Control plane is not configured" }, { status: 503 });
  }
  const reviewer = request.headers.get("x-deployai-reviewer-actor-id");
  if (!reviewer) {
    return NextResponse.json(
      { error: "X-Deployai-Reviewer-Actor-Id header is required" },
      { status: 400 },
    );
  }
  const url = `${base.replace(/\/$/, "")}/internal/v1/tenants/${tenant}/schema-proposals/${proposalId}/reject`;
  const r = await fetch(url, {
    method: "POST",
    headers: {
      "X-DeployAI-Internal-Key": key,
      "X-Deployai-Reviewer-Actor-Id": reviewer,
      "content-type": "application/json",
    },
    body: JSON.stringify({ rejection_reason: body.rejection_reason ?? "" }),
    cache: "no-store",
  });
  const text = await r.text();
  return new NextResponse(text, {
    status: r.status,
    headers: { "content-type": r.headers.get("content-type") ?? "application/json" },
  });
}
