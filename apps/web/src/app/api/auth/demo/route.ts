import { NextResponse } from "next/server";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";
import { demoRateLimited } from "@/lib/internal/demo-rate-limit";
import { accessTokenCookieNameFromEnv } from "@/lib/internal/deployai-access-jwt";
import {
  parseCpSessionIssued,
  secureCookiesFromRedirectUri,
  sessionTenantCookieNameFromEnv,
} from "@/lib/internal/oidc-web-flow";

/**
 * Zero-friction guest demo login (Wave 4S showcase).
 *
 * `GET /api/auth/demo` — the target of the login page's "View live demo"
 * button. Server-side it calls the control plane's
 * `POST /internal/v1/demo/session` with the internal key (never exposed to the
 * browser); the CP mints a short-TTL access JWT with the single `demo_guest`
 * role on the disposable demo tenant. That JWT lands in the same
 * `deployai_access_token` cookie the OIDC callback sets (same attributes), so
 * the existing middleware Path A (DEPLOYAI_WEB_TRUST_JWT=1 + PEM) verifies it
 * with no new code. Then 303 → /engagements.
 *
 * Gates, in order:
 *   1. `NEXT_PUBLIC_DEMO_MODE !== "1"` → 404 (route effectively absent).
 *   2. Naive per-IP rate limit → 429 (single-instance, in-memory — see
 *      src/lib/internal/demo-rate-limit.ts for the honest limitation notes).
 *   3. CP demo endpoint disabled/misconfigured (CP 404) → 404 here too.
 *   4. CP unreachable/failed → 302 /login?error=demo_unavailable.
 *
 * The refresh token the CP returns is intentionally dropped: demo sessions
 * simply expire after the access-token TTL (15 min default) and the visitor
 * can click the button again.
 *
 * Residual risk (stated plainly): `demo_guest` holds `canonical:read` only,
 * which denies /admin and /api/internal/v1 at the middleware — but BFF
 * mutation routes that gate with `canonical:read` today (single proposal
 * accept/reject, review-item resolve/dismiss, insight actions, onboarding
 * seeds) remain callable by a demo session. Accepted for wave 1 because every
 * such write is confined to the disposable demo tenant by the authz
 * cross-tenant rule + tenancy/RLS. Never enable demo mode on a deployment
 * that hosts customer tenants.
 */

function clientIp(request: Request): string {
  const xff = request.headers.get("x-forwarded-for");
  return xff?.split(",")[0]?.trim() || "unknown";
}

/**
 * Origin for redirects. Behind a proxy (Railway/Fly) `request.url`'s host is
 * the container bind address (e.g. 0.0.0.0:3000) — a redirect built from it
 * sends the browser nowhere. Prefer the forwarded host/proto headers.
 */
function requestOrigin(request: Request): string {
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  const proto = request.headers.get("x-forwarded-proto") ?? "https";
  if (host) return `${proto}://${host}`;
  return new URL(request.url).origin;
}

export async function GET(request: Request): Promise<NextResponse> {
  if (process.env.NEXT_PUBLIC_DEMO_MODE !== "1") {
    return new NextResponse("Not Found", { status: 404 });
  }
  if (demoRateLimited(clientIp(request))) {
    return new NextResponse("demo-rate-limited (try again in a minute)", { status: 429 });
  }

  const cpBase = getControlPlaneBaseUrl();
  const internalKey = getControlPlaneInternalKey();
  if (!cpBase || !internalKey) {
    return new NextResponse("control-plane-not-configured", { status: 503 });
  }

  let cpRes: Response;
  try {
    cpRes = await fetch(`${cpBase.replace(/\/$/, "")}/internal/v1/demo/session`, {
      method: "POST",
      cache: "no-store",
      headers: { "X-DeployAI-Internal-Key": internalKey },
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    return NextResponse.redirect(
      new URL("/login?error=demo_unavailable", requestOrigin(request)),
      302,
    );
  }

  if (cpRes.status === 404) {
    // CP demo mode is off (or misconfigured) — mirror it so probes see the
    // same thing as when NEXT_PUBLIC_DEMO_MODE is unset.
    return new NextResponse("Not Found", { status: 404 });
  }
  if (!cpRes.ok) {
    return NextResponse.redirect(
      new URL("/login?error=demo_unavailable", requestOrigin(request)),
      302,
    );
  }

  let body: unknown;
  try {
    body = await cpRes.json();
  } catch {
    body = null;
  }
  const session = parseCpSessionIssued(body);
  if (!session) {
    return NextResponse.redirect(
      new URL("/login?error=demo_unavailable", requestOrigin(request)),
      302,
    );
  }

  // Same cookie attributes as the OIDC callback route. Demo deploys may not
  // configure OIDC at all, so also mark Secure whenever the request itself is
  // https. No refresh cookie — a demo session just expires.
  const secure = secureCookiesFromRedirectUri() || requestOrigin(request).startsWith("https:");
  const res = NextResponse.redirect(new URL("/engagements", requestOrigin(request)), 303);
  res.cookies.set(accessTokenCookieNameFromEnv(), session.access_token, {
    maxAge: session.expires_in,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure,
  });
  res.cookies.set(sessionTenantCookieNameFromEnv(), session.tenant_id, {
    maxAge: session.expires_in,
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure,
  });
  return res;
}
