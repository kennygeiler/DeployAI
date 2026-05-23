/**
 * Sprint 1 inc 2 — non-SCIM tenant user provisioning client.
 *
 * Wraps the CP `POST /internal/v1/tenants/{tid}/users` admin route used
 * by the first-run wizard. SCIM (`/scim/v2/Users`) stays the supported
 * production path for IdP-driven provisioning; this is the bootstrap
 * seam for self-hosted single-team installs.
 */
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type AppUser = {
  id: string;
  tenant_id: string;
  user_name: string;
  email: string | null;
  given_name: string | null;
  family_name: string | null;
  active: boolean;
  created_at: string;
};

export type AppUserCreate = {
  user_name: string;
  email?: string | null;
  given_name?: string | null;
  family_name?: string | null;
};

function cpHeaders(): Record<string, string> {
  const key = getControlPlaneInternalKey();
  if (!key) {
    throw new Error("DEPLOYAI_INTERNAL_API_KEY not set");
  }
  return { "X-DeployAI-Internal-Key": key };
}

function cpBase(): string {
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  if (!base) {
    throw new Error("DEPLOYAI_CONTROL_PLANE_URL not set");
  }
  return base;
}

export async function cpCreateTenantUser(tenantId: string, body: AppUserCreate): Promise<AppUser> {
  const url = `${cpBase()}/internal/v1/tenants/${encodeURIComponent(tenantId)}/users`;
  const r = await fetch(url, {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp tenant user create ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as AppUser;
}
