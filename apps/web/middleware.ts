import { NextResponse, type NextRequest } from "next/server";

import { canAccess, type Action, type Resource, type V1Role } from "@deployai/authz";

const isAdmin = (p: string) =>
  p === "/admin/runs" || p === "/admin/adjudication" || p.startsWith("/admin/schema-proposals");

const isStrategistSurface = (p: string) =>
  p === "/digest" ||
  p === "/in-meeting" ||
  p === "/phase-tracking" ||
  p === "/evening" ||
  p.startsWith("/evidence/") ||
  p === "/action-queue" ||
  p === "/validation-queue" ||
  p === "/solidification-review" ||
  p === "/overrides" ||
  p.startsWith("/audit/");

/** BFF + internal routes the strategist shell polls; need the same actor as pages. */
const isStrategistApi = (p: string) =>
  p.startsWith("/api/bff/") || p === "/api/internal/strategist-activity";

function shouldRunAuthz(pathname: string): boolean {
  return isAdmin(pathname) || isStrategistSurface(pathname) || isStrategistApi(pathname);
}

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
  if (isStrategistSurface(pathname) || isStrategistApi(pathname)) {
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
  if (isStrategistSurface(pathname) || isStrategistApi(pathname)) {
    return { kind: "canonical_memory" };
  }
  return { kind: "global" };
}

export function middleware(request: NextRequest) {
  const requestHeaders = new Headers(request.headers);
  if (
    process.env.NODE_ENV === "development" &&
    process.env.DEPLOYAI_DISABLE_DEV_STRATEGIST !== "1" &&
    !requestHeaders.get("x-deployai-role")
  ) {
    requestHeaders.set("x-deployai-role", "deployment_strategist");
  }

  const { pathname } = request.nextUrl;
  if (!shouldRunAuthz(pathname)) {
    return NextResponse.next({ request: { headers: requestHeaders } });
  }
  const role = parseRole(requestHeaders.get("x-deployai-role"));
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
  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: [
    "/digest",
    "/in-meeting",
    "/action-queue",
    "/phase-tracking",
    "/evening",
    "/evidence/:path*",
    "/validation-queue",
    "/solidification-review",
    "/overrides",
    "/audit/:path*",
    "/api/bff/:path*",
    "/api/internal/strategist-activity",
    "/admin/runs",
    "/admin/adjudication",
    "/admin/schema-proposals",
    "/admin/schema-proposals/:path*",
  ],
};
