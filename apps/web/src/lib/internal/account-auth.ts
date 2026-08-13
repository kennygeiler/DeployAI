/**
 * Shared plumbing for the native email/password BFF routes
 * (`/api/auth/signin`, `/api/auth/signup`, `/api/auth/change-password`,
 * `/api/auth/invites*`, `/api/auth/me`).
 *
 * The control plane owns credentials + session minting (`/api/v1/auth/*`);
 * these helpers only translate a CP session payload into the SAME web
 * cookies the OIDC callback route sets (deployai_access_token /
 * deployai_refresh_token / deployai_session_tenant, identical attributes) so
 * middleware, refresh, and logout work unchanged for password sessions.
 */

import { NextResponse } from "next/server";

import { accessTokenCookieNameFromEnv } from "@/lib/internal/deployai-access-jwt";
import {
  parseCookieHeader,
  refreshCookieMaxAgeFromEnv,
  refreshTokenCookieNameFromEnv,
  secureCookiesFromRedirectUri,
  sessionTenantCookieNameFromEnv,
  type CpOidcSessionIssued,
} from "@/lib/internal/oidc-web-flow";

export function selfServeSignupEnabled(): boolean {
  return process.env.NEXT_PUBLIC_SELF_SERVE_SIGNUP === "1";
}

/** Behind a proxy the request host is the bind address; prefer forwarded headers. */
export function requestOrigin(request: Request): string {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  const proto = request.headers.get("x-forwarded-proto") ?? "https";
  if (host) {
    return `${proto}://${host}`;
  }
  return new URL(request.url).origin;
}

/** Same rule as the demo route: Secure when OIDC says so OR the request is https. */
export function secureCookiesForRequest(request: Request): boolean {
  return secureCookiesFromRedirectUri() || requestOrigin(request).startsWith("https:");
}

/** Session cookies with the exact attributes the OIDC callback route uses. */
export function applySessionCookies(
  res: NextResponse,
  session: CpOidcSessionIssued,
  secure: boolean,
): NextResponse {
  const refreshMaxAge = refreshCookieMaxAgeFromEnv();
  res.cookies.set(accessTokenCookieNameFromEnv(), session.access_token, {
    maxAge: session.expires_in,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure,
  });
  res.cookies.set(refreshTokenCookieNameFromEnv(), session.refresh_token, {
    maxAge: refreshMaxAge,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure,
  });
  res.cookies.set(sessionTenantCookieNameFromEnv(), session.tenant_id, {
    maxAge: refreshMaxAge,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure,
  });
  return res;
}

/** Access JWT from the session cookie (for authed CP calls made by BFF routes). */
export function accessTokenFromRequest(request: Request): string | null {
  const cookies = parseCookieHeader(request.headers.get("cookie"));
  return cookies.get(accessTokenCookieNameFromEnv()) ?? null;
}

/**
 * Forward a CP error response with a safe JSON body. Only the CP's `detail`
 * string is passed through (CP writes human-safe messages for these routes);
 * anything unparsable becomes a generic message.
 */
export async function forwardCpError(cpRes: Response): Promise<NextResponse> {
  let detail = "Request failed. Please try again.";
  try {
    const body: unknown = await cpRes.json();
    if (
      body &&
      typeof body === "object" &&
      typeof (body as { detail?: unknown }).detail === "string"
    ) {
      detail = (body as { detail: string }).detail;
    }
  } catch {
    // keep the generic message
  }
  return NextResponse.json({ error: detail }, { status: cpRes.status });
}
