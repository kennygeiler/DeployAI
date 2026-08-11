import { NextResponse } from "next/server";
import * as jose from "jose";

import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";
import { accessTokenCookieNameFromEnv } from "@/lib/internal/deployai-access-jwt";
import {
  parseCookieHeader,
  refreshTokenCookieNameFromEnv,
  secureCookiesFromRedirectUri,
  sessionTenantCookieNameFromEnv,
} from "@/lib/internal/oidc-web-flow";

/**
 * Logout (ticket A1): best-effort revoke the CP refresh session
 * (`POST {CP}/auth/logout`), clear the session cookies, redirect to /login.
 * Revocation needs the tenant id; prefer the dedicated tenant cookie, fall
 * back to the (possibly expired) access JWT's `tid` claim — decode only, the
 * CP validates tenant/JTI match server-side.
 */
async function handleLogout(request: Request): Promise<NextResponse> {
  const cookies = parseCookieHeader(request.headers.get("cookie"));
  const accessCookieName = accessTokenCookieNameFromEnv();
  const refreshCookieName = refreshTokenCookieNameFromEnv();
  const tenantCookieName = sessionTenantCookieNameFromEnv();

  const refreshToken = cookies.get(refreshCookieName) ?? null;
  let tenantId = cookies.get(tenantCookieName) ?? null;
  if (!tenantId) {
    const access = cookies.get(accessCookieName);
    if (access) {
      try {
        const tid = jose.decodeJwt(access).tid;
        tenantId = typeof tid === "string" && tid ? tid : null;
      } catch {
        tenantId = null;
      }
    }
  }

  const cpBase = getControlPlaneBaseUrl();
  if (cpBase && refreshToken && tenantId) {
    try {
      await fetch(`${cpBase.replace(/\/$/, "")}/auth/logout`, {
        method: "POST",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId, refresh_token: refreshToken }),
        signal: AbortSignal.timeout(5000),
      });
    } catch {
      // Best-effort: still clear cookies locally when the CP is unreachable.
    }
  }

  const res = NextResponse.redirect(new URL("/login", request.url), 303);
  const secure = secureCookiesFromRedirectUri();
  for (const name of [accessCookieName, refreshCookieName, tenantCookieName]) {
    res.cookies.set(name, "", { maxAge: 0, httpOnly: true, sameSite: "lax", path: "/", secure });
  }
  return res;
}

export async function POST(request: Request): Promise<NextResponse> {
  return handleLogout(request);
}

/** Allow plain-link logout (browser navigation). */
export async function GET(request: Request): Promise<NextResponse> {
  return handleLogout(request);
}
