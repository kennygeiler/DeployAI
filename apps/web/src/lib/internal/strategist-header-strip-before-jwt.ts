/**
 * Path A hosted pilot: optionally delete inbound strategist headers before JWT-derived
 * identity is applied (`DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT`).
 * Used by `apps/web/middleware.ts`.
 *
 * @see docs/pilot/session-and-headers.md
 * @see docs/production/identity-and-tenancy.md
 */
export function shouldStripInboundStrategistHeadersBeforeJwt(): boolean {
  return (
    process.env.DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT === "1" &&
    process.env.DEPLOYAI_WEB_TRUST_JWT === "1" &&
    !!process.env.DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM?.trim()
  );
}

/** Delete `x-deployai-role` / `x-deployai-tenant` when the strip policy is active. */
export function stripInboundStrategistHeadersBeforeJwt(headers: Headers): void {
  if (!shouldStripInboundStrategistHeadersBeforeJwt()) {
    return;
  }
  headers.delete("x-deployai-role");
  headers.delete("x-deployai-tenant");
}
