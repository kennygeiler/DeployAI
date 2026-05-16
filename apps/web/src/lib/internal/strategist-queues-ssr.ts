import { listSolidificationQueue } from "@/lib/bff/strategist-queues-store";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";
import {
  strategistQueuesShouldRejectMemoryFallback,
  strategistQueuesUseControlPlane,
} from "@/lib/internal/strategist-queues-backend";
import { cpListSolidificationQueue } from "@/lib/internal/strategist-queues-cp";

function solidificationPendingCount(rows: { state: string }[]): number {
  return rows.filter((r) => r.state === "unresolved" || r.state === "in-review").length;
}

export async function getSolidificationPendingCountForStrategistPage(
  tenantId: string | null,
): Promise<number> {
  const tid = tenantId?.trim();
  if (
    strategistQueuesUseControlPlane() &&
    tid &&
    getControlPlaneBaseUrl() &&
    getControlPlaneInternalKey()
  ) {
    const rows = await cpListSolidificationQueue(tid);
    return solidificationPendingCount(rows);
  }
  if (strategistQueuesShouldRejectMemoryFallback(tenantId)) {
    throw new Error(
      "Strategist queues: CP backend selected but DEPLOYAI_CONTROL_PLANE_URL / DEPLOYAI_INTERNAL_API_KEY missing (break-glass: DEPLOYAI_STRATEGIST_QUEUE_CP_ALLOW_MEMORY_FALLBACK=1)",
    );
  }
  return solidificationPendingCount(listSolidificationQueue(tenantId));
}
