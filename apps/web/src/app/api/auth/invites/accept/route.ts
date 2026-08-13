import { NextResponse } from "next/server";

import {
  applySessionCookies,
  forwardCpError,
  secureCookiesForRequest,
} from "@/lib/internal/account-auth";
import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";
import { parseCpSessionIssued, postLoginPathFromEnv } from "@/lib/internal/oidc-web-flow";

/**
 * Redeem an invite: the CP creates the user in the invite's tenant with the
 * invite's role + password credential and mints a session, which lands in
 * the standard session cookies so the invitee arrives signed in.
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
  const b = (body ?? {}) as { token?: unknown; password?: unknown; display_name?: unknown };
  if (
    typeof b.token !== "string" ||
    !b.token ||
    typeof b.password !== "string" ||
    !b.password ||
    typeof b.display_name !== "string" ||
    !b.display_name.trim()
  ) {
    return NextResponse.json(
      { error: "token, password, and display_name are required" },
      { status: 400 },
    );
  }
  let cpRes: Response;
  try {
    cpRes = await fetch(`${cpBase.replace(/\/$/, "")}/api/v1/auth/invites/accept`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        token: b.token,
        password: b.password,
        display_name: b.display_name.trim(),
      }),
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
  const res = NextResponse.json({ ok: true, next: postLoginPathFromEnv() }, { status: 201 });
  return applySessionCookies(res, session, secureCookiesForRequest(request));
}
