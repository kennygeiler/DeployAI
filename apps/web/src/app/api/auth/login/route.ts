import { NextResponse } from "next/server";

import {
  buildAuthorizeUrl,
  fetchOpenidMetadata,
  OIDC_NONCE_COOKIE,
  OIDC_STATE_COOKIE,
  OIDC_TRANSIENT_COOKIE_MAX_AGE,
  OIDC_VERIFIER_COOKIE,
  OidcIssuerUnreachableError,
  oidcClientIdFromEnv,
  oidcIssuerFromEnv,
  oidcRedirectUriFromEnv,
  oidcWebLoginConfigured,
  pkcePair,
  randomUrlSafeToken,
  secureCookiesFromRedirectUri,
} from "@/lib/internal/oidc-web-flow";

/**
 * Start OIDC + PKCE sign-in (ticket A1). Generates state / nonce / PKCE,
 * stores them in short-lived HttpOnly cookies on the web origin, and
 * redirects the browser to the issuer's authorize endpoint. The callback
 * (`/api/auth/callback/oidc`) forwards those cookies to the control plane,
 * which performs the code exchange and mints the session.
 */
export async function GET(request: Request): Promise<NextResponse> {
  if (!oidcWebLoginConfigured()) {
    return new NextResponse("oidc-not-configured", { status: 503 });
  }
  const issuer = oidcIssuerFromEnv()!;
  const clientId = oidcClientIdFromEnv()!;
  const redirectUri = oidcRedirectUriFromEnv()!;

  let metadata;
  try {
    metadata = await fetchOpenidMetadata(issuer);
  } catch (e) {
    if (e instanceof OidcIssuerUnreachableError) {
      return NextResponse.redirect(new URL("/login?error=issuer_unreachable", request.url), 302);
    }
    throw e;
  }

  const state = randomUrlSafeToken(32);
  const nonce = randomUrlSafeToken(16);
  const { verifier, challenge } = await pkcePair();
  const authorizeUrl = buildAuthorizeUrl({
    metadata,
    clientId,
    redirectUri,
    state,
    codeChallenge: challenge,
    nonce,
  });

  const res = NextResponse.redirect(authorizeUrl, 302);
  const secure = secureCookiesFromRedirectUri();
  for (const [name, value] of [
    [OIDC_STATE_COOKIE, state],
    [OIDC_VERIFIER_COOKIE, verifier],
    [OIDC_NONCE_COOKIE, nonce],
  ] as const) {
    res.cookies.set(name, value, {
      maxAge: OIDC_TRANSIENT_COOKIE_MAX_AGE,
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      secure,
    });
  }
  return res;
}
