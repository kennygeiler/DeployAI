import { decideSync } from "@deployai/authz";
import { NextResponse } from "next/server";

import { getActorFromHeaders } from "@/lib/internal/actor";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

/**
 * List recent ingestion runs (control-plane). Epic 3 Story 3-8.
 */
export async function GET() {
  const actor = await getActorFromHeaders();
  if (!actor) {
    return new NextResponse("Unauthorized", { status: 401 });
  }
  const d = decideSync(actor, "ingest:view_runs", { kind: "ingestion_runs" });
  if (!d.allow) {
    return new NextResponse("Forbidden", { status: 403 });
  }
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
  const url = `${base.replace(/\/$/, "")}/internal/v1/ingestion-runs?limit=100`;
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
