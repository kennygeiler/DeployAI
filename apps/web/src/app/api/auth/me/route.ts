import { NextResponse } from "next/server";

import { accessTokenFromRequest, forwardCpError } from "@/lib/internal/account-auth";
import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";

/**
 * Session profile for the /account page: proxies `GET {CP}/api/v1/auth/me`
 * with the access JWT from the HttpOnly session cookie (the browser can
 * never read the token itself).
 */
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
    cpRes = await fetch(`${cpBase.replace(/\/$/, "")}/api/v1/auth/me`, {
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
  return NextResponse.json(body ?? {});
}
