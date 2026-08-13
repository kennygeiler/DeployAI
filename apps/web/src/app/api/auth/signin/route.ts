import { NextResponse } from "next/server";

import {
  applySessionCookies,
  forwardCpError,
  secureCookiesForRequest,
} from "@/lib/internal/account-auth";
import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";
import { parseCpSessionIssued, postLoginPathFromEnv } from "@/lib/internal/oidc-web-flow";

/**
 * Native email/password sign-in. Server-side call to the CP's
 * `POST /api/v1/auth/login` (uniform 401s + attempt limiting live there);
 * on success the CP session lands in the same cookies the OIDC callback
 * sets, and the client navigates to `next`.
 */
export async function POST(request: Request): Promise<NextResponse> {
  const cpBase = getControlPlaneBaseUrl();
  if (!cpBase) {
    return NextResponse.json({ error: "control-plane-not-configured" }, { status: 503 });
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = null;
  }
  const b = (body ?? {}) as { email?: unknown; password?: unknown };
  if (typeof b.email !== "string" || !b.email || typeof b.password !== "string" || !b.password) {
    return NextResponse.json({ error: "email and password are required" }, { status: 400 });
  }

  let cpRes: Response;
  try {
    cpRes = await fetch(`${cpBase.replace(/\/$/, "")}/api/v1/auth/login`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: b.email, password: b.password }),
      signal: AbortSignal.timeout(15000),
    });
  } catch {
    return NextResponse.json({ error: "control-plane-unreachable" }, { status: 502 });
  }
  if (!cpRes.ok) {
    return forwardCpError(cpRes);
  }
  const session = parseCpSessionIssued(await cpRes.json().catch(() => null));
  if (!session) {
    return NextResponse.json({ error: "invalid session response" }, { status: 502 });
  }
  const res = NextResponse.json({ ok: true, next: postLoginPathFromEnv() });
  return applySessionCookies(res, session, secureCookiesForRequest(request));
}
