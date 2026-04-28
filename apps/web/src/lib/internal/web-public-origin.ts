import { headers } from "next/headers";

/** Public browser origin for OAuth `return_to` URLs (Epic 16.2). */
export async function getPublicOriginFromHeaders(): Promise<string> {
  const h = await headers();
  const host = h.get("x-forwarded-host") ?? h.get("host") ?? "localhost:3000";
  const proto = h.get("x-forwarded-proto") ?? "http";
  return `${proto}://${host}`;
}
