import { NextResponse } from "next/server";

import {
  accessTokenFromRequest,
  applySessionCookies,
  forwardCpError,
  secureCookiesForRequest,
} from "@/lib/internal/account-auth";
import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";
import { parseCpSessionIssued } from "@/lib/internal/oidc-web-flow";

/**
 * Change password (authed). The CP verifies the current password, stores a
 * fresh argon2id hash, revokes EVERY refresh session for the user, and mints
 * a replacement pair — which this route swaps into the session cookies so the
 * current browser stays signed in while all other sessions die at refresh.
 */
export async function POST(request: Request): Promise<NextResponse> {
  const cpBase = getControlPlaneBaseUrl();
  if (!cpBase) {
    return NextResponse.json({ error: "control-plane-not-configured" }, { status: 503 });
  }
  const token = accessTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ error: "not signed in" }, { status: 401 });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = null;
  }
  const b = (body ?? {}) as { current_password?: unknown; new_password?: unknown };
  if (
    typeof b.current_password !== "string" ||
    !b.current_password ||
    typeof b.new_password !== "string" ||
    !b.new_password
  ) {
    return NextResponse.json(
      { error: "current_password and new_password are required" },
      { status: 400 },
    );
  }
  let cpRes: Response;
  try {
    cpRes = await fetch(`${cpBase.replace(/\/$/, "")}/api/v1/auth/password`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ current_password: b.current_password, new_password: b.new_password }),
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    return NextResponse.json({ error: "control-plane-unreachable" }, { status: 502 });
  }
  if (!cpRes.ok) {
    return forwardCpError(cpRes);
  }
  const session = parseCpSessionIssued(await cpRes.json().catch(() => null));
  const res = NextResponse.json({ ok: true });
  if (session) {
    return applySessionCookies(res, session, secureCookiesForRequest(request));
  }
  return res;
}
