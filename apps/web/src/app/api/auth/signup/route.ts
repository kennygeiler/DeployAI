import { NextResponse } from "next/server";

import {
  applySessionCookies,
  forwardCpError,
  secureCookiesForRequest,
  selfServeSignupEnabled,
} from "@/lib/internal/account-auth";
import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";
import { parseCpSessionIssued, postLoginPathFromEnv } from "@/lib/internal/oidc-web-flow";

/**
 * Self-serve workspace creation. Double-gated like demo mode: 404 unless
 * `NEXT_PUBLIC_SELF_SERVE_SIGNUP=1` here, AND the CP enforces its own
 * `DEPLOYAI_SELF_SERVE_SIGNUP` (a CP 404 is mirrored). On success the creator
 * lands authed via the same cookies as every other login path.
 */
export async function POST(request: Request): Promise<NextResponse> {
  if (!selfServeSignupEnabled()) {
    return new NextResponse("Not Found", { status: 404 });
  }
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
  const b = (body ?? {}) as {
    email?: unknown;
    password?: unknown;
    workspace_name?: unknown;
    display_name?: unknown;
  };
  if (
    typeof b.email !== "string" ||
    !b.email ||
    typeof b.password !== "string" ||
    !b.password ||
    typeof b.workspace_name !== "string" ||
    !b.workspace_name.trim() ||
    typeof b.display_name !== "string" ||
    !b.display_name.trim()
  ) {
    return NextResponse.json(
      { error: "email, password, workspace_name, and display_name are required" },
      { status: 400 },
    );
  }

  let cpRes: Response;
  try {
    cpRes = await fetch(`${cpBase.replace(/\/$/, "")}/api/v1/auth/signup`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: b.email,
        password: b.password,
        workspace_name: b.workspace_name.trim(),
        display_name: b.display_name.trim(),
      }),
      signal: AbortSignal.timeout(20000),
    });
  } catch {
    return NextResponse.json({ error: "control-plane-unreachable" }, { status: 502 });
  }
  if (cpRes.status === 404) {
    // CP-side gate is off — mirror it (same posture as the demo route).
    return new NextResponse("Not Found", { status: 404 });
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
