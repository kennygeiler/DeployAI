import { NextResponse, type NextRequest } from "next/server";

import { canAccess, type Action, type Resource, type V1Role } from "@deployai/authz";

const isAdmin = (p: string) =>
  p === "/admin/runs" || p === "/admin/adjudication" || p.startsWith("/admin/schema-proposals");

const isStrategistSurface = (p: string) =>
  p === "/digest" || p === "/phase-tracking" || p === "/evening";

function parseRole(r: string | null): V1Role | null {
  const allowed: V1Role[] = [
    "platform_admin",
    "customer_admin",
    "deployment_strategist",
    "successor_strategist",
    "customer_records_officer",
    "external_auditor",
  ];
  if (!r) {
    return null;
  }
  return (allowed as string[]).includes(r) ? (r as V1Role) : null;
}

function actionForPath(pathname: string): Action {
  if (isStrategistSurface(pathname)) {
    return "canonical:read";
  }
  if (pathname.startsWith("/admin/schema-proposals")) {
    return "admin:view_schema_proposals";
  }
  if (pathname === "/admin/adjudication") {
    return "eval:view_adjudication";
  }
  return "ingest:view_runs";
}

function resourceForPath(pathname: string): Resource {
  if (isStrategistSurface(pathname)) {
    return { kind: "canonical_memory" };
  }
  return { kind: "global" };
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (!isAdmin(pathname) && !isStrategistSurface(pathname)) {
    return NextResponse.next();
  }
  const role = parseRole(request.headers.get("x-deployai-role"));
  if (!role) {
    return new NextResponse("Forbidden: missing or invalid x-deployai-role (see docs).", {
      status: 403,
    });
  }
  const a = actionForPath(pathname);
  const r = resourceForPath(pathname);
  const d = canAccess({ role }, a, r, { skipAudit: true });
  if (!d.allow) {
    return new NextResponse("Forbidden: role cannot access this surface in V1.", {
      status: 403,
    });
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/digest",
    "/phase-tracking",
    "/evening",
    "/admin/runs",
    "/admin/adjudication",
    "/admin/schema-proposals",
    "/admin/schema-proposals/:path*",
  ],
};
