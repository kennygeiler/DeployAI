import { NextResponse, type NextRequest } from "next/server";

import { canAccess, type Action, type Resource, type V1Role } from "@deployai/authz";

import {
  accessTokenCookieNameFromEnv,
  applyDeployaiAccessJwtToHeaders,
} from "@/lib/internal/deployai-access-jwt";
import { stripInboundStrategistHeadersBeforeJwt } from "@/lib/internal/strategist-header-strip-before-jwt";
import { ensureRequestCorrelationHeader } from "@/lib/internal/correlation-id";

const isAdmin = (p: string) =>
  p === "/admin/runs" || p === "/admin/adjudication" || p.startsWith("/admin/schema-proposals");

const isStrategistSurface = (p: string) =>
  p === "/engagements" ||
  p.startsWith("/engagements/") ||
  p === "/digest" ||
  p === "/in-meeting" ||
  p === "/phase-tracking" ||
  p === "/evening" ||
  p.startsWith("/evidence/") ||
  p === "/action-queue" ||
  p === "/validation-queue" ||
  p === "/solidification-review" ||
  p === "/overrides" ||
  p.startsWith("/audit/") ||
  p === "/settings/integrations";

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
    "fde",
    "biz_dev",
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
  ensureRequestCorrelationHeader(requestHeaders, request.headers);
  /** Hosted SSO hardening: strip forged inbound headers before JWT replaces actor (see docs/pilot/session-and-headers.md). */
  stripInboundStrategistHeadersBeforeJwt(requestHeaders);
  const cookieName = accessTokenCookieNameFromEnv();
  const jwtGate = await applyDeployaiAccessJwtToHeaders(
    request.headers.get("authorization"),
    request.cookies.get(cookieName)?.value ?? null,
    requestHeaders,
  );
  if (jwtGate?.invalidToken) {
    return new NextResponse("Unauthorized: invalid or expired access token", { status: 401 });
  }
  // Dev-only role injection. Triggers when EITHER:
  //   - `next dev` (process.env.NODE_ENV === "development", inlined by Next), OR
  //   - DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1 at runtime (escape hatch for the
  //     local Docker compose stack, which runs the production build but still
  //     wants header auto-injection so engineers can hit pages without an SSO
  //     proxy or a browser extension).
  // NEVER set DEPLOYAI_LOCAL_DEV_ROLE_INJECT in a hosted/pilot deploy.
  // Override the injected role — e.g. to test as fde or biz_dev — with
  // DEPLOYAI_DEV_STRATEGIST_ROLE.
  const devRoleInjectEnabled =
    process.env.NODE_ENV === "development" || process.env.DEPLOYAI_LOCAL_DEV_ROLE_INJECT === "1";
  if (
    devRoleInjectEnabled &&
    process.env.DEPLOYAI_DISABLE_DEV_STRATEGIST !== "1" &&
    !requestHeaders.get("x-deployai-role")
  ) {
    requestHeaders.set(
      "x-deployai-role",
      process.env.DEPLOYAI_DEV_STRATEGIST_ROLE?.trim() || "deployment_strategist",
    );
  }
  // Tenant injection — symmetric with role injection. BFF routes call
  // `actor.tenantId!.trim()` and 500 if tenant is missing, so we must supply
  // one whenever we supply a role. Defaults to the seed_app.py tenant.
  if (devRoleInjectEnabled && !requestHeaders.get("x-deployai-tenant")) {
    requestHeaders.set(
      "x-deployai-tenant",
      process.env.DEPLOYAI_DEV_TENANT_ID?.trim() || "11111111-1111-1111-1111-111111111111",
    );
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
    if (
      role === "external_auditor" &&
      (isStrategistSurface(pathname) || isStrategistApi(pathname))
    ) {
      return new NextResponse(
        "Forbidden: external_auditor cannot access strategist / canonical-memory surfaces (Epic 12 Story 12.3). Use provisioned FOIA export flows — not digest, evidence, or BFF routes.",
        { status: 403 },
      );
    }
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
    "/engagements",
    "/engagements/:path*",
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
    "/settings/integrations",
    "/api/bff/:path*",
    "/api/internal/strategist-activity",
    "/admin/runs",
    "/admin/adjudication",
    "/admin/schema-proposals",
    "/admin/schema-proposals/:path*",
  ],
};
