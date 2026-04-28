import { NextResponse, type NextRequest } from "next/server";

import { canAccess, type Action, type Resource, type V1Role } from "@deployai/authz";

import {
  accessTokenCookieNameFromEnv,
  applyDeployaiAccessJwtToHeaders,
} from "@/lib/internal/deployai-access-jwt";

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

function strategistPathRequiresTenant(pathname: string): boolean {
  return isStrategistSurface(pathname) || isStrategistApi(pathname);
}

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

export async function middleware(request: NextRequest) {
  const requestHeaders = new Headers(request.headers);
  const cookieName = accessTokenCookieNameFromEnv();
  const jwtGate = await applyDeployaiAccessJwtToHeaders(
    request.headers.get("authorization"),
    request.cookies.get(cookieName)?.value ?? null,
    requestHeaders,
  );
  if (jwtGate?.invalidToken) {
    return new NextResponse("Unauthorized: invalid or expired access token", { status: 401 });
  }
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
  if (
    process.env.DEPLOYAI_STRATEGIST_REQUIRE_TENANT === "1" &&
    strategistPathRequiresTenant(pathname) &&
    !requestHeaders.get("x-deployai-tenant")?.trim()
  ) {
    return new NextResponse(
      "Forbidden: missing x-deployai-tenant (pilot/staging: set headers from IdP/proxy or DEPLOYAI_STRATEGIST_REQUIRE_TENANT=0 — see docs/pilot/session-and-headers.md).",
      { status: 403 },
    );
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
