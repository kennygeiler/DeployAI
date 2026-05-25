import { NextResponse } from "next/server";

// Phase D inc 1b — OIDC callback stub. When DEPLOYAI_OIDC_ISSUER is unset
// the route returns 503 ("oidc-not-configured") so dev / compose traffic
// surfaces the missing-credential state cleanly. When the issuer IS set
// the route still 501s ("oidc-callback-stub-pending-jwt-verify") because
// owner-credentialed wiring (issuer JWKS fetch + id_token verification +
// session-mint) lands in a follow-up slice. See docs/auth/oidc.md.
//
// TODO(owner-creds): once DEPLOYAI_OIDC_CLIENT_SECRET is provisioned,
// replace the 501 branch with the real callback handler:
//   1. exchange `code` for tokens against the issuer token endpoint
//   2. fetch JWKS, verify id_token signature + iss/aud/nonce/exp
//   3. JIT app_users by `sub`; mint the deployai-access JWT
//   4. set the access + refresh cookies via the same helpers the
//      control-plane uses on /auth/oidc/callback
// The control-plane OIDC settings (DEPLOYAI_OIDC_*) and the JWT signing
// keys (DEPLOYAI_JWT_PRIVATE_KEY_PATH) are already wired in
// services/control-plane/src/control_plane/config/settings.py.

export function GET(): NextResponse {
  if (!process.env.DEPLOYAI_OIDC_ISSUER) {
    return new NextResponse("oidc-not-configured", { status: 503 });
  }
  return new NextResponse("oidc-callback-stub-pending-jwt-verify", { status: 501 });
}
