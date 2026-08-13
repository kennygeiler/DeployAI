import { NextResponse } from "next/server";

import { accessTokenFromRequest, forwardCpError, requestOrigin } from "@/lib/internal/account-auth";
import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";

/**
 * Workspace invites (admin-only; the CP enforces the role from the JWT).
 *
 * POST creates a single-use invite and returns `join_url` — the CP's
 * relative `join_path` prefixed with this deployment's own origin. There is
 * no email delivery anywhere in the stack: the admin copies the link and
 * sends it out of band, and this response is the only time the raw token
 * exists outside the invitee's browser.
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
  const b = (body ?? {}) as { email?: unknown; role?: unknown };
  if (typeof b.email !== "string" || !b.email || typeof b.role !== "string" || !b.role) {
    return NextResponse.json({ error: "email and role are required" }, { status: 400 });
  }
  let cpRes: Response;
  try {
    cpRes = await fetch(`${cpBase.replace(/\/$/, "")}/api/v1/auth/invites`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ email: b.email, role: b.role }),
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    return NextResponse.json({ error: "control-plane-unreachable" }, { status: 502 });
  }
  if (!cpRes.ok) {
    return forwardCpError(cpRes);
  }
  const created: unknown = await cpRes.json().catch(() => null);
  const c = (created ?? {}) as Record<string, unknown>;
  const joinPath = typeof c.join_path === "string" ? c.join_path : null;
  if (!joinPath || !joinPath.startsWith("/join/")) {
    return NextResponse.json({ error: "invalid invite response" }, { status: 502 });
  }
  return NextResponse.json(
    {
      invite_id: c.invite_id,
      email: c.email,
      role: c.role,
      expires_at: c.expires_at,
      join_url: `${requestOrigin(request)}${joinPath}`,
    },
    { status: 201 },
  );
}

/** Pending (unaccepted, unexpired) invites for the caller's tenant. */
export async function GET(request: Request): Promise<NextResponse> {
  const cpBase = getControlPlaneBaseUrl();
  if (!cpBase) {
    return NextResponse.json({ error: "control-plane-not-configured" }, { status: 503 });
  }
  const token = accessTokenFromRequest(request);
  if (!token) {
    return NextResponse.json({ error: "not signed in" }, { status: 401 });
  }
  let cpRes: Response;
  try {
    cpRes = await fetch(`${cpBase.replace(/\/$/, "")}/api/v1/auth/invites`, {
      method: "GET",
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(10000),
    });
  } catch {
    return NextResponse.json({ error: "control-plane-unreachable" }, { status: 502 });
  }
  if (!cpRes.ok) {
    return forwardCpError(cpRes);
  }
  const body: unknown = await cpRes.json().catch(() => null);
  return NextResponse.json(Array.isArray(body) ? body : []);
}
