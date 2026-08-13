import { NextResponse } from "next/server";

import { forwardCpError } from "@/lib/internal/account-auth";
import { getControlPlaneBaseUrl } from "@/lib/internal/control-plane";

/**
 * Public invite preview for the /join/[token] page: what workspace + role the
 * link grants, before the invitee sets a password. Invalid/expired/used
 * tokens are a single generic 404 (the CP does not distinguish them).
 */
export async function GET(request: Request): Promise<NextResponse> {
  const cpBase = getControlPlaneBaseUrl();
  if (!cpBase) {
    return NextResponse.json({ error: "control-plane-not-configured" }, { status: 503 });
  }
  const token = new URL(request.url).searchParams.get("token");
  if (!token) {
    return NextResponse.json({ error: "token is required" }, { status: 400 });
  }
  const cpUrl = new URL(`${cpBase.replace(/\/$/, "")}/api/v1/auth/invites/preview`);
  cpUrl.searchParams.set("token", token);
  let cpRes: Response;
  try {
    cpRes = await fetch(cpUrl, {
      method: "GET",
      cache: "no-store",
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
