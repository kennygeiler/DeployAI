import { NextResponse } from "next/server";

import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";
import { requestOrigin } from "@/lib/internal/account-auth";
import { accessTokenCookieNameFromEnv } from "@/lib/internal/deployai-access-jwt";
import {
  OIDC_NONCE_COOKIE,
  OIDC_STATE_COOKIE,
  OIDC_VERIFIER_COOKIE,
  oidcWebLoginConfigured,
  parseCookieHeader,
  parseCpSessionIssued,
  postLoginPathFromEnv,
  refreshCookieMaxAgeFromEnv,
  refreshTokenCookieNameFromEnv,
  secureCookiesFromRedirectUri,
  sessionTenantCookieNameFromEnv,
} from "@/lib/internal/oidc-web-flow";

/**
 * OIDC callback (ticket A1). Validates state against the HttpOnly cookie set
 * by `/api/auth/login`, then delegates the sensitive half of the flow to the
 * control plane's `GET /auth/oidc/callback` (code exchange with the client
 * secret, JWKS ID-token verification of iss/aud/exp + nonce, JIT user
 * provisioning, RS256 session mint + Redis refresh session), forwarding the
 * state / verifier / nonce cookies the CP expects. On success the CP-minted
 * access JWT (claims sub / tid / roles / token_use=access) is set as the
 * cookie the existing middleware verifies via deployai-access-jwt.ts.
 *
 * Failure mapping:
 *   - OIDC env not configured ................ 503 "oidc-not-configured"
 *   - IdP redirected back with an error ...... 302 -> /login?error=idp_error
 *   - missing/mismatched state cookie ........ 400
 *   - CP says token exchange/verify failed ... 400
 *   - unknown user with JIT disabled (CP 403). 403
 *   - issuer unreachable (CP 502) ............ 302 -> /login?error=issuer_unreachable
 *   - CP unreachable ......................... 302 -> /login?error=control_plane_unreachable
 */
export async function GET(request: Request): Promise<NextResponse> {
  if (!oidcWebLoginConfigured()) {
    return new NextResponse("oidc-not-configured", { status: 503 });
  }

  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const idpError = url.searchParams.get("error");
  if (idpError) {
    return NextResponse.redirect(new URL("/login?error=idp_error", requestOrigin(request)), 302);
  }
  if (!code || !state) {
    return new NextResponse("oidc-missing-code-or-state", { status: 400 });
  }

  const cookies = parseCookieHeader(request.headers.get("cookie"));
  const cState = cookies.get(OIDC_STATE_COOKIE);
  const cVerifier = cookies.get(OIDC_VERIFIER_COOKIE);
  const cNonce = cookies.get(OIDC_NONCE_COOKIE);
  if (!cState || !cVerifier || !cNonce || cState !== state) {
    return new NextResponse("oidc-state-mismatch (retry login)", { status: 400 });
  }

  const cpBase = getControlPlaneBaseUrl();
  if (!cpBase) {
    return new NextResponse("control-plane-not-configured", { status: 503 });
  }

  const cpUrl = new URL(`${cpBase.replace(/\/$/, "")}/auth/oidc/callback`);
  cpUrl.searchParams.set("code", code);
  cpUrl.searchParams.set("state", state);

  let cpRes: Response;
  try {
    cpRes = await fetch(cpUrl, {
      method: "GET",
      cache: "no-store",
      redirect: "manual",
      headers: {
        cookie: [
          `${OIDC_STATE_COOKIE}=${cState}`,
          `${OIDC_VERIFIER_COOKIE}=${cVerifier}`,
          `${OIDC_NONCE_COOKIE}=${cNonce}`,
        ].join("; "),
      },
      signal: AbortSignal.timeout(30000),
    });
  } catch {
    return NextResponse.redirect(
      new URL("/login?error=control_plane_unreachable", requestOrigin(request)),
      302,
    );
  }

  const secure = secureCookiesFromRedirectUri();
  const clearTransient = (res: NextResponse): NextResponse => {
    for (const name of [OIDC_STATE_COOKIE, OIDC_VERIFIER_COOKIE, OIDC_NONCE_COOKIE]) {
      res.cookies.set(name, "", { maxAge: 0, httpOnly: true, sameSite: "lax", path: "/", secure });
    }
    return res;
  };

  if (cpRes.status === 502) {
    // CP could not reach the issuer (metadata / token endpoint).
    return clearTransient(
      NextResponse.redirect(
        new URL("/login?error=issuer_unreachable", requestOrigin(request)),
        302,
      ),
    );
  }
  if (cpRes.status === 403) {
    return clearTransient(
      new NextResponse("oidc-user-not-provisioned (JIT provisioning disabled)", { status: 403 }),
    );
  }
  if (cpRes.status === 400) {
    // Covers bad code, failed exchange, bad ID-token signature, iss/aud/exp/nonce failures.
    return clearTransient(new NextResponse("oidc-token-verification-failed", { status: 400 }));
  }
  if (cpRes.status === 503) {
    return clearTransient(new NextResponse("oidc-not-configured", { status: 503 }));
  }
  if (!cpRes.ok) {
    return clearTransient(
      NextResponse.redirect(new URL("/login?error=sso_failed", requestOrigin(request)), 302),
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
    return clearTransient(
      NextResponse.redirect(new URL("/login?error=sso_failed", requestOrigin(request)), 302),
    );
  }

  const res = NextResponse.redirect(new URL(postLoginPathFromEnv(), request.url), 303);
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
  return clearTransient(res);
}
