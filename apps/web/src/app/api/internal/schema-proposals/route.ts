import { decideSync } from "@deployai/authz";
import { type NextRequest, NextResponse } from "next/server";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

function isUuid(s: string): boolean {
  return /^[0-9a-fA-F-]{36}$/.test(s);
}

/**
 * List pending (or other status) schema proposals for a tenant.
 * Query: tenant (required), status (default pending)
 */
export async function GET(request: NextRequest) {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "admin:view_schema_proposals", { kind: "schema_proposals" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
  const q = request.nextUrl.searchParams;
  const tenant = q.get("tenant")?.trim() ?? "";
  if (!tenant || !isUuid(tenant)) {
    return NextResponse.json({ error: "Query ?tenant=<uuid> is required" }, { status: 400 });
  }
  const status = q.get("status")?.trim() || "pending";
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return NextResponse.json(
      {
        error:
          "Control plane is not configured (set DEPLOYAI_CONTROL_PLANE_URL and DEPLOYAI_INTERNAL_API_KEY on the web server)",
      },
      { status: 503 },
    );
  }
  const url = `${base.replace(/\/$/, "")}/internal/v1/tenants/${tenant}/schema-proposals?status=${encodeURIComponent(status)}`;
  const r = await fetch(url, {
    headers: { "X-DeployAI-Internal-Key": key },
    cache: "no-store",
  });
  const text = await r.text();
  return new NextResponse(text, {
    status: r.status,
    headers: { "content-type": r.headers.get("content-type") ?? "application/json" },
  });
}
