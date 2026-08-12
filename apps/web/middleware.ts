import { NextResponse, type NextRequest } from "next/server";

import { canAccess, type Action, type Resource, type V1Role } from "@deployai/authz";

import {
  accessTokenCookieNameFromEnv,
  applyDeployaiAccessJwtToHeaders,
} from "@/lib/internal/deployai-access-jwt";
import {
  devInjectedRole,
  devInjectedTenantId,
  devRoleInjectEnabled,
} from "@/lib/internal/dev-role-inject";
import { stripInboundStrategistHeadersBeforeJwt } from "@/lib/internal/strategist-header-strip-before-jwt";
import { ensureRequestCorrelationHeader } from "@/lib/internal/correlation-id";

const isStrategistSurface = (p: string) =>
  p === "/engagements" ||
  p.startsWith("/engagements/") ||
  p === "/search" ||
  p.startsWith("/search/") ||
  p === "/settings" ||
  p.startsWith("/settings/") ||
  p === "/onboarding" ||
  p.startsWith("/onboarding/");

/** BFF routes the strategist shell polls; need the same actor as pages. */
const isStrategistApi = (p: string) => p.startsWith("/api/bff/");

/** Admin pages (Agent Kenny dashboard / MCP activity). Wave 1 ticket A2. */
const isAdminSurface = (p: string) => p === "/admin" || p.startsWith("/admin/");

/** Internal v1 proxy routes (`/api/internal/v1/...`). Wave 1 ticket A2. */
const isInternalApi = (p: string) => p.startsWith("/api/internal/");

function shouldRunAuthz(pathname: string): boolean {
  return (
    isStrategistSurface(pathname) ||
    isStrategistApi(pathname) ||
    isAdminSurface(pathname) ||
    isInternalApi(pathname)
  );
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
    "demo_guest",
  ];
  if (!r) {
    return null;
  }
  return (allowed as string[]).includes(r) ? (r as V1Role) : null;
}

function actionForPath(pathname: string): Action {
  if (isAdminSurface(pathname)) {
    return "admin:read";
  }
  if (isInternalApi(pathname)) {
    return "internal:proxy";
  }
  return "canonical:read";
}

/**
 * Tenant the request is about: the `/api/internal/v1/tenants/{tid}/...` path
 * segment when present, else the (JWT-derived or proxy-supplied) tenant header.
 */
function requestTenantId(pathname: string, requestHeaders: Headers): string | null {
  const m = /^\/api\/internal\/v1\/tenants\/([^/]+)(?:\/|$)/.exec(pathname);
  if (m?.[1]) {
    return decodeURIComponent(m[1]).trim() || null;
  }
  return requestHeaders.get("x-deployai-tenant")?.trim() || null;
}

function resourceForPath(pathname: string, requestHeaders: Headers): Resource {
  return {
    kind: "canonical_memory",
    tenantId: requestTenantId(pathname, requestHeaders) ?? undefined,
  };
}

/**
 * Tenant is required by default on every gated path. Opt OUT with
 * `DEPLOYAI_STRATEGIST_REQUIRE_TENANT=0` — local dev only, never hosted.
 */
function tenantRequired(): boolean {
  return process.env.DEPLOYAI_STRATEGIST_REQUIRE_TENANT !== "0";
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
  // Dev-only role injection — strictly opt-in (DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1,
  // plus DEPLOYAI_DEV_ROLE_INJECT_ALLOW_PRODUCTION=1 on production builds such as
  // the local compose stack). See src/lib/internal/dev-role-inject.ts.
  // NEVER set these flags in a hosted/pilot deploy.
  if (devRoleInjectEnabled()) {
    if (!requestHeaders.get("x-deployai-role")) {
      requestHeaders.set("x-deployai-role", devInjectedRole());
    }
    // Tenant injection — symmetric with role injection. BFF routes call
    // `actor.tenantId!.trim()` and 500 if tenant is missing, so we must supply
    // one whenever we supply a role. Defaults to the seed_app.py tenant.
    if (!requestHeaders.get("x-deployai-tenant")) {
      requestHeaders.set("x-deployai-tenant", devInjectedTenantId());
    }
  }

  const { pathname } = request.nextUrl;
  if (!shouldRunAuthz(pathname)) {
    return NextResponse.next({ request: { headers: requestHeaders } });
  }
  const role = parseRole(requestHeaders.get("x-deployai-role"));
  if (!role) {
    // Browser page loads get the login page, not a bare 403 — API callers
    // (and anything not asking for HTML) keep the machine-readable status.
    const wantsHtml = request.headers.get("accept")?.includes("text/html") ?? false;
    const isPageRequest = wantsHtml && !pathname.startsWith("/api/");
    if (isPageRequest) {
      const loginUrl = request.nextUrl.clone();
      loginUrl.pathname = "/login";
      loginUrl.search = "";
      loginUrl.searchParams.set("next", pathname);
      return NextResponse.redirect(loginUrl);
    }
    return new NextResponse("Forbidden: missing or invalid x-deployai-role (see docs).", {
      status: 403,
    });
  }
  if (tenantRequired() && !requestHeaders.get("x-deployai-tenant")?.trim()) {
    return new NextResponse(
      "Forbidden: missing x-deployai-tenant (pilot/staging: set headers from IdP/proxy — see docs/pilot/session-and-headers.md; DEPLOYAI_STRATEGIST_REQUIRE_TENANT=0 disables this check for local dev only).",
      { status: 403 },
    );
  }
  const a = actionForPath(pathname);
  const r = resourceForPath(pathname, requestHeaders);
  let allow: boolean;
  try {
    allow = canAccess(
      { role, tenantId: requestHeaders.get("x-deployai-tenant")?.trim() || undefined },
      a,
      r,
      {
        skipAudit: true,
      },
    ).allow;
  } catch {
    // canAccess throws outside production when no tenant could be derived for a
    // tenant-scoped resource (only reachable with DEPLOYAI_STRATEGIST_REQUIRE_TENANT=0
    // and no tenant header). Fail closed rather than 500.
    allow = false;
  }
  if (!allow) {
    if (role === "external_auditor") {
      return new NextResponse(
        "Forbidden: external_auditor cannot access engagement / canonical-memory surfaces. Use provisioned export flows instead.",
        { status: 403 },
      );
    }
    return new NextResponse("Forbidden: role cannot access this surface in V1.", {
      status: 403,
    });
  }
  return NextResponse.next({ request: { headers: requestHeaders } });
}

export const config = {
  matcher: [
    "/engagements",
    "/engagements/:path*",
    "/search",
    "/search/:path*",
    "/settings",
    "/settings/:path*",
    "/onboarding",
    "/onboarding/:path*",
    "/admin",
    "/admin/:path*",
    "/api/bff/:path*",
    "/api/internal/:path*",
  ],
};
