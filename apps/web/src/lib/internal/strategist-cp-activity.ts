import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type StrategistActivityPayload = {
  tenantId: string;
  actorId: string;
  category: string;
  summary: string;
  detail: Record<string, unknown>;
  refId?: string | null;
};

/** Best-effort CP append for personal audit (Epic 10.7); no throw when unconfigured. */
export async function postStrategistActivityToCp(payload: StrategistActivityPayload): Promise<boolean> {
  const base = getControlPlaneBaseUrl()?.replace(/\/$/, "");
  const key = getControlPlaneInternalKey();
  if (!base?.trim() || !key?.trim()) {
    return false;
  }
  const url = `${base}/internal/v1/strategist/activity-events`;
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-DeployAI-Internal-Key": key,
      },
      body: JSON.stringify({
        tenant_id: payload.tenantId,
        actor_id: payload.actorId,
        category: payload.category,
        summary: payload.summary,
        detail: payload.detail,
        ref_id: payload.refId ?? null,
      }),
    });
    return r.ok;
  } catch {
    return false;
  }
}
