import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

/**
 * Strategist BFF queue routes always use the control-plane Postgres-backed
 * `/internal/v1/strategist/*-queue` APIs. There is no in-process queue store.
 */
export function strategistQueuesCpMisconfiguredForTenant(
  tenantId: string | null | undefined,
): boolean {
  const tid = tenantId?.trim();
  if (!tid) {
    return false;
  }
  return !getControlPlaneBaseUrl() || !getControlPlaneInternalKey();
}
