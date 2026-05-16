import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

/**
 * When `DEPLOYAI_STRATEGIST_QUEUES_BACKEND=cp`, BFF queue routes proxy to the control-plane
 * `/internal/v1/strategist/*-queue-items` APIs (Postgres-backed).
 *
 * Default remains in-memory `strategist-queues-store` for local demos without CP.
 */
export function strategistQueuesUseControlPlane(): boolean {
  return process.env.DEPLOYAI_STRATEGIST_QUEUES_BACKEND === "cp";
}

export function strategistQueuesCpMisconfiguredForTenant(tenantId: string | null | undefined): boolean {
  const tid = tenantId?.trim();
  if (!strategistQueuesUseControlPlane() || !tid) {
    return false;
  }
  return !getControlPlaneBaseUrl() || !getControlPlaneInternalKey();
}

/**
 * In production, do not fall back to in-process queue state when CP mode is selected.
 * Break-glass: `DEPLOYAI_STRATEGIST_QUEUE_CP_ALLOW_MEMORY_FALLBACK=1`.
 */
export function strategistQueuesShouldRejectMemoryFallback(tenantId: string | null | undefined): boolean {
  if (!strategistQueuesCpMisconfiguredForTenant(tenantId)) {
    return false;
  }
  if (process.env.DEPLOYAI_STRATEGIST_QUEUE_CP_ALLOW_MEMORY_FALLBACK === "1") {
    return false;
  }
  return process.env.NODE_ENV === "production";
}
