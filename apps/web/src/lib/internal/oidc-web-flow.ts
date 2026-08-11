/**
 * Web-side OIDC login helpers (ticket A1).
 *
 * The web app owns the browser-facing half of the OIDC flow:
 *
 *   1. `GET /api/auth/login` generates state / nonce / PKCE, stores them in
 *      short-lived HttpOnly cookies, and redirects to the issuer's authorize
 *      endpoint.
 *   2. `GET /api/auth/callback/oidc` validates state against the cookie, then
 *      delegates code exchange + JWKS ID-token verification + JIT user
 *      provisioning + session minting to the control plane
 *      (`GET {CP}/auth/oidc/callback`), forwarding the transient cookies the
 *      CP expects (`dep_oidc_state` / `dep_oidc_verifier` / `dep_oidc_nonce`).
 *   3. The CP-minted RS256 access JWT (claims: sub / tid / roles / iss / aud /
 *      iat / exp / jti / token_use=access) is stored in the cookie the
 *      existing middleware already verifies (see deployai-access-jwt.ts), so
 *      no new verification code is needed on the web side.
 *
 * Config comes from the same env names the control plane uses
 * (DEPLOYAI_OIDC_ISSUER / DEPLOYAI_OIDC_CLIENT_ID / DEPLOYAI_OIDC_REDIRECT_URI).
 * The client secret stays in the CP only — the web app never touches it.
 */

// Transient cookie names match the CP's own login flow so the callback can
// forward them verbatim to `GET {CP}/auth/oidc/callback`.
export const OIDC_STATE_COOKIE = "dep_oidc_state";
export const OIDC_VERIFIER_COOKIE = "dep_oidc_verifier";
export const OIDC_NONCE_COOKIE = "dep_oidc_nonce";
export const OIDC_TRANSIENT_COOKIE_MAX_AGE = 600;

export function oidcIssuerFromEnv(): string | null {
  const v = process.env.DEPLOYAI_OIDC_ISSUER?.trim();
  return v || null;
}

export function oidcClientIdFromEnv(): string | null {
  const v = process.env.DEPLOYAI_OIDC_CLIENT_ID?.trim();
  return v || null;
}

export function oidcRedirectUriFromEnv(): string | null {
  const v = process.env.DEPLOYAI_OIDC_REDIRECT_URI?.trim();
  return v || null;
}

/** True when the web app has everything it needs to start a login. */
export function oidcWebLoginConfigured(): boolean {
  return Boolean(oidcIssuerFromEnv() && oidcClientIdFromEnv() && oidcRedirectUriFromEnv());
}

export function refreshTokenCookieNameFromEnv(): string {
  return process.env.DEPLOYAI_WEB_REFRESH_TOKEN_COOKIE ?? "deployai_refresh_token";
}

/**
 * HttpOnly tenant-id cookie set alongside the session so logout can revoke the
 * CP refresh session even after the access JWT has expired.
 */
export function sessionTenantCookieNameFromEnv(): string {
  return process.env.DEPLOYAI_WEB_SESSION_TENANT_COOKIE ?? "deployai_session_tenant";
}

export function postLoginPathFromEnv(): string {
  const v = process.env.DEPLOYAI_OIDC_POST_LOGIN_PATH?.trim();
  return v && v.startsWith("/") ? v : "/engagements";
}

/** Refresh cookie lifetime; keep aligned with the CP's refresh TTL (7 days). */
export function refreshCookieMaxAgeFromEnv(): number {
  const raw = process.env.DEPLOYAI_WEB_REFRESH_COOKIE_MAX_AGE;
  const n = raw ? Number.parseInt(raw, 10) : Number.NaN;
  return Number.isFinite(n) && n > 0 ? n : 7 * 24 * 60 * 60;
}

/** Mirror the CP: cookies are Secure iff the registered redirect URI is https. */
export function secureCookiesFromRedirectUri(): boolean {
  const uri = oidcRedirectUriFromEnv();
  if (!uri) {
    return false;
  }
  try {
    return new URL(uri).protocol === "https:";
  } catch {
    return false;
  }
}

function base64UrlEncode(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) {
    bin += String.fromCharCode(b);
  }
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function randomUrlSafeToken(byteLength = 32): string {
  const bytes = new Uint8Array(byteLength);
  crypto.getRandomValues(bytes);
  return base64UrlEncode(bytes);
}

async function getSubtle(): Promise<SubtleCrypto> {
  if (globalThis.crypto?.subtle) {
    return globalThis.crypto.subtle;
  }
  // Test environments (jsdom) may not expose WebCrypto's subtle API.
  const { webcrypto } = await import("node:crypto");
  return webcrypto.subtle as SubtleCrypto;
}

/** RFC 7636 S256 pair, matching the CP's `pkce_pair()`. */
export async function pkcePair(): Promise<{ verifier: string; challenge: string }> {
  const verifier = randomUrlSafeToken(48);
  const subtle = await getSubtle();
  const digest = await subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return { verifier, challenge: base64UrlEncode(new Uint8Array(digest)) };
}

export class OidcIssuerUnreachableError extends Error {}

export type OpenidMetadata = {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  jwks_uri: string;
};

/**
 * Fetch `{issuer}/.well-known/openid-configuration`. Throws
 * OidcIssuerUnreachableError on network failure, non-2xx, or missing fields.
 */
export async function fetchOpenidMetadata(
  issuer: string,
  timeoutMs = 10000,
): Promise<OpenidMetadata> {
  const url = `${issuer.replace(/\/$/, "")}/.well-known/openid-configuration`;
  let r: Response;
  try {
    r = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(timeoutMs) });
  } catch (e) {
    throw new OidcIssuerUnreachableError(`openid configuration fetch failed: ${String(e)}`);
  }
  if (!r.ok) {
    throw new OidcIssuerUnreachableError(`openid configuration fetch failed: ${r.status}`);
  }
  let data: unknown;
  try {
    data = await r.json();
  } catch {
    throw new OidcIssuerUnreachableError("openid configuration is not JSON");
  }
  const md = data as Partial<OpenidMetadata>;
  for (const key of ["issuer", "authorization_endpoint", "token_endpoint", "jwks_uri"] as const) {
    if (typeof md[key] !== "string" || !md[key]) {
      throw new OidcIssuerUnreachableError(`openid metadata missing ${key}`);
    }
  }
  return md as OpenidMetadata;
}

/** Same parameters (scope, S256, query response mode) the CP flow uses. */
export function buildAuthorizeUrl(args: {
  metadata: OpenidMetadata;
  clientId: string;
  redirectUri: string;
  state: string;
  codeChallenge: string;
  nonce: string;
}): string {
  const q = new URLSearchParams({
    client_id: args.clientId,
    response_type: "code",
    redirect_uri: args.redirectUri,
    scope: "openid email profile",
    state: args.state,
    code_challenge: args.codeChallenge,
    code_challenge_method: "S256",
    response_mode: "query",
    nonce: args.nonce,
  });
  return `${args.metadata.authorization_endpoint}?${q.toString()}`;
}

/** Minimal request-cookie-header parser (avoids next/headers in unit tests). */
export function parseCookieHeader(header: string | null): Map<string, string> {
  const out = new Map<string, string>();
  if (!header) {
    return out;
  }
  for (const part of header.split(";")) {
    const i = part.indexOf("=");
    if (i <= 0) {
      continue;
    }
    const name = part.slice(0, i).trim();
    const value = part.slice(i + 1).trim();
    if (name && !out.has(name)) {
      out.set(name, value);
    }
  }
  return out;
}

/** Shape of the CP `GET /auth/oidc/callback` 200 response we consume. */
export type CpOidcSessionIssued = {
  access_token: string;
  refresh_token: string;
  tenant_id: string;
  expires_in: number;
};

export function parseCpSessionIssued(body: unknown): CpOidcSessionIssued | null {
  if (typeof body !== "object" || body === null) {
    return null;
  }
  const b = body as Record<string, unknown>;
  if (
    typeof b.access_token !== "string" ||
    !b.access_token ||
    typeof b.refresh_token !== "string" ||
    !b.refresh_token ||
    typeof b.tenant_id !== "string" ||
    !b.tenant_id
  ) {
    return null;
  }
  const expiresIn =
    typeof b.expires_in === "number" && Number.isFinite(b.expires_in) && b.expires_in > 0
      ? b.expires_in
      : 15 * 60;
  return {
    access_token: b.access_token,
    refresh_token: b.refresh_token,
    tenant_id: b.tenant_id,
    expires_in: expiresIn,
  };
}
