import type { AuthActor } from "@deployai/authz";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";

export type StrategistIntegrationRecord = {
  id: string;
  provider: string;
  display_name: string;
  state: string;
  disabled_at: string | null;
};

export type StrategistIntegrationRecordsLoad =
  | { status: "unconfigured" }
  | { status: "error" }
  | { status: "ok"; items: readonly StrategistIntegrationRecord[] };

function parseRecords(json: unknown): readonly StrategistIntegrationRecord[] | null {
  if (typeof json !== "object" || json === null || !("items" in json)) {
    return null;
  }
  const items = (json as { items: unknown }).items;
  if (!Array.isArray(items)) {
    return null;
  }
  const out: StrategistIntegrationRecord[] = [];
  for (const row of items) {
    if (typeof row !== "object" || row === null) {
      return null;
    }
    const r = row as Record<string, unknown>;
    if (
      typeof r.id !== "string" ||
      typeof r.provider !== "string" ||
      typeof r.display_name !== "string" ||
      typeof r.state !== "string"
    ) {
      return null;
    }
    const da = r.disabled_at;
    out.push({
      id: r.id,
      provider: r.provider,
      display_name: r.display_name,
      state: r.state,
      disabled_at: da === null || typeof da === "string" ? da : null,
    });
  }
  return out;
}

/** Epic 16.3 — internal CP integration rows for the strategist tenant (no tokens). */
export async function loadStrategistIntegrationRecords(
  actor: AuthActor | null,
): Promise<StrategistIntegrationRecordsLoad> {
  const tid = actor?.tenantId?.trim();
  if (!tid) {
    return { status: "ok", items: [] };
  }
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return { status: "unconfigured" };
  }
  const u = `${base.replace(/\/$/, "")}/internal/v1/strategist/integration-records?tenant_id=${encodeURIComponent(tid)}`;
  try {
    const r = await fetch(u, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) {
      return { status: "error" };
    }
    const parsed = parseRecords(await r.json());
    if (!parsed) {
      return { status: "error" };
    }
    return { status: "ok", items: parsed };
  } catch {
    return { status: "error" };
  }
}
