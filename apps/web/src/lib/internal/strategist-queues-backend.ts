/**
 * When `DEPLOYAI_STRATEGIST_QUEUES_BACKEND=cp`, BFF queue routes proxy to the control-plane
 * `/internal/v1/strategist/*-queue-items` APIs (Postgres-backed).
 *
 * Default remains in-memory `strategist-queues-store` for local demos without CP.
 */
export function strategistQueuesUseControlPlane(): boolean {
  return process.env.DEPLOYAI_STRATEGIST_QUEUES_BACKEND === "cp";
}
