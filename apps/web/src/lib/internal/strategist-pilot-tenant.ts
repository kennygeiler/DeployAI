/**
 * One-tenant pilot: when `DEPLOYAI_PILOT_TENANT_ID` matches the signed-in tenant,
 * strategist surfaces load from the control plane (same paths as `DEPLOYAI_*_SOURCE=cp`)
 * without setting per-surface `STRATEGIST_*_SOURCE_URL` overrides.
 */

import type { AuthActor } from "@deployai/authz";

export function getDeployAiPilotTenantId(): string | null {
  const v = process.env.DEPLOYAI_PILOT_TENANT_ID?.trim();
  return v || null;
}

export function actorIsDeployAiPilotTenant(tenantId: string | null | undefined): boolean {
  const pilot = getDeployAiPilotTenantId();
  if (!pilot || !tenantId?.trim()) {
    return false;
  }
  return tenantId.trim() === pilot;
}

function actorTenant(actor: AuthActor | null): string | null | undefined {
  return actor?.tenantId;
}

/** Morning digest from CP file / future canonical projections. */
export function digestSurfacesUseControlPlane(actor: AuthActor | null): boolean {
  if (process.env.DEPLOYAI_DIGEST_SOURCE?.trim() === "cp") {
    return true;
  }
  return actorIsDeployAiPilotTenant(actorTenant(actor));
}

/** Evidence deeplink from CP pilot surface. */
export function evidenceSurfacesUseControlPlane(actor: AuthActor | null): boolean {
  if (process.env.DEPLOYAI_EVIDENCE_SOURCE?.trim() === "cp") {
    return true;
  }
  return actorIsDeployAiPilotTenant(actorTenant(actor));
}

/** Phase tracking from CP pilot surface file. */
export function phaseTrackingSurfacesUseControlPlane(actor: AuthActor | null): boolean {
  if (process.env.DEPLOYAI_PHASE_TRACKING_SOURCE?.trim() === "cp") {
    return true;
  }
  return actorIsDeployAiPilotTenant(actorTenant(actor));
}

/** Evening synthesis from CP pilot surface file. */
export function eveningSynthesisSurfacesUseControlPlane(actor: AuthActor | null): boolean {
  if (process.env.DEPLOYAI_EVENING_SYNTHESIS_SOURCE?.trim() === "cp") {
    return true;
  }
  return actorIsDeployAiPilotTenant(actorTenant(actor));
}
