/**
 * Control-plane intake-address API (internal key) — Wave 5 IN2.
 *
 * Proxies the CP's per-engagement inbound-email address endpoints
 * (`GET /internal/v1/engagements/{id}/intake-address` + `POST .../regenerate`).
 * The CP mints the address lazily on first read; regenerate revokes the old
 * one. See `docs/ops/intake-email.md` for the delivery pipeline.
 */
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type IntakeAddress = {
  local_part: string;
  /** Full address when the CP has DEPLOYAI_INTAKE_EMAIL_DOMAIN set, else null. */
  email: string | null;
  created_at: string;
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

function addressUrl(tenantId: string, engagementId: string, suffix = ""): string {
  return (
    `${cpBase()}/internal/v1/engagements/${encodeURIComponent(engagementId)}/intake-address${suffix}` +
    `?tenant_id=${encodeURIComponent(tenantId)}`
  );
}

export async function cpGetIntakeAddress(
  tenantId: string,
  engagementId: string,
): Promise<IntakeAddress> {
  const r = await fetch(addressUrl(tenantId, engagementId), {
    method: "GET",
    headers: cpHeaders(),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp intake-address ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as IntakeAddress;
}

export async function cpRegenerateIntakeAddress(
  tenantId: string,
  engagementId: string,
  actorId: string | null,
): Promise<IntakeAddress> {
  const r = await fetch(addressUrl(tenantId, engagementId, "/regenerate"), {
    method: "POST",
    headers: { ...cpHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ actor_id: actorId }),
    cache: "no-store",
  });
  if (!r.ok) {
    throw new Error(`cp intake-address regenerate ${r.status}: ${await r.text()}`);
  }
  return (await r.json()) as IntakeAddress;
}
