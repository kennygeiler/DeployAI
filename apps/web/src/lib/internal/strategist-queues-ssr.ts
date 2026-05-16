import { strategistQueuesCpMisconfiguredForTenant } from "@/lib/internal/strategist-queues-backend";
import { cpListSolidificationQueue } from "@/lib/internal/strategist-queues-cp";

function solidificationPendingCount(rows: { state: string }[]): number {
  return rows.filter((r) => r.state === "unresolved" || r.state === "in-review").length;
}

export async function getSolidificationPendingCountForStrategistPage(
  tenantId: string | null,
): Promise<number> {
  const tid = tenantId?.trim();
  if (!tid) {
    return 0;
  }
  if (strategistQueuesCpMisconfiguredForTenant(tid)) {
    throw new Error(
      "Strategist queues: DEPLOYAI_CONTROL_PLANE_URL / DEPLOYAI_INTERNAL_API_KEY missing (solidification count requires control plane)",
    );
  }
  const rows = await cpListSolidificationQueue(tid);
  return solidificationPendingCount(rows);
}
