import { decideSync, type AuthActor } from "@deployai/authz";

import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "./control-plane";
import { getStrategistLocalDateForServer } from "./strategist-local-date";

/**
 * Ingestion run row from `GET /internal/v1/ingestion-runs` (control plane).
 * Shapes the Python `IngestionRunRead` / admin runs table.
 */
type CpIngestionRun = {
  tenant_id: string;
  status: string;
};

export type StrategistActivitySnapshot = {
  agentDegraded: boolean;
  ingestionInProgress: boolean;
  /** Mock surfaces + due-window chips: strategist calendar date (YYYY-MM-DD). */
  strategistLocalDate: string;
  /** `ok` — CP list fetched; `unconfigured` — no URL/key; `error` — non-2xx or network failure. */
  controlPlane: "ok" | "unconfigured" | "error";
};

/**
 * Health + running-ingest for strategist chrome (FR46/FR47). Agent “degrade” in V1 is
 * “control plane unavailable for this check” (no separate Oracle service endpoint yet).
 */
export async function loadStrategistActivityForActor(
  actor: AuthActor | null,
): Promise<StrategistActivitySnapshot> {
  const day = getStrategistLocalDateForServer();
  if (!actor) {
    return {
      agentDegraded: false,
      ingestionInProgress: false,
      strategistLocalDate: day,
      controlPlane: "unconfigured",
    };
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return {
      agentDegraded: false,
      ingestionInProgress: false,
      strategistLocalDate: day,
      controlPlane: "unconfigured",
    };
  }
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return {
      agentDegraded: false,
      ingestionInProgress: false,
      strategistLocalDate: day,
      controlPlane: "unconfigured",
    };
  }
  const url = `${base.replace(/\/$/, "")}/internal/v1/ingestion-runs?limit=200`;
  try {
    const r = await fetch(url, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
    });
    if (!r.ok) {
      return {
        agentDegraded: true,
        ingestionInProgress: false,
        strategistLocalDate: day,
        controlPlane: "error",
      };
    }
    const runs = (await r.json()) as CpIngestionRun[];
    if (!Array.isArray(runs)) {
      return {
        agentDegraded: true,
        ingestionInProgress: false,
        strategistLocalDate: day,
        controlPlane: "error",
      };
    }
    const tid = actor.tenantId?.trim() ?? null;
    const scoped = tid ? runs.filter((x) => x.tenant_id === tid) : runs;
    const running = scoped.filter((x) => x.status === "running");
    return {
      agentDegraded: false,
      ingestionInProgress: running.length > 0,
      strategistLocalDate: day,
      controlPlane: "ok",
    };
  } catch {
    return {
      agentDegraded: true,
      ingestionInProgress: false,
      strategistLocalDate: day,
      controlPlane: "error",
    };
  }
}
