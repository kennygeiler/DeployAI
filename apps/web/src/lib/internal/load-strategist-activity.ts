import { decideSync, type AuthActor } from "@deployai/authz";

import {
  fetchControlPlaneHealthzOk,
  fetchOptionalOracleServiceHealth,
} from "./control-plane-fetch";
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

export type AgentServiceHealth = "unconfigured" | "ok" | "error";

export type StrategistActivitySnapshot = {
  agentDegraded: boolean;
  ingestionInProgress: boolean;
  strategistLocalDate: string;
  /** `ok` — CP list fetched; `unconfigured` — no URL/key; `error` — health or ingest path failed. */
  controlPlane: "ok" | "unconfigured" | "error";
  /**
   * Optional Oracle (or other agent) HTTP liveness. `unconfigured` when
   * `DEPLOYAI_ORACLE_HEALTH_URL` is unset. When `error` and not unconfigured, surfaces degrade.
   */
  agentServiceHealth: AgentServiceHealth;
};

function snapshot(
  day: string,
  partial: Omit<StrategistActivitySnapshot, "strategistLocalDate">,
): StrategistActivitySnapshot {
  return { strategistLocalDate: day, ...partial };
}

/**
 * Health + running-ingest for strategist chrome (FR46/FR47).
 * - Liveness: `GET {controlPlane}/healthz` before internal APIs.
 * - Ingest: `GET /internal/v1/ingestion-runs` (tenant-scoped; **no** tenant id ⇒ no running rows / FR47).
 * - Optional agents: `GET DEPLOYAI_ORACLE_HEALTH_URL` when set.
 */
export async function loadStrategistActivityForActor(
  actor: AuthActor | null,
): Promise<StrategistActivitySnapshot> {
  const day = getStrategistLocalDateForServer();
  if (!actor) {
    return snapshot(day, {
      agentDegraded: false,
      ingestionInProgress: false,
      controlPlane: "unconfigured",
      agentServiceHealth: "unconfigured",
    });
  }
  const d = decideSync(actor, "canonical:read", { kind: "canonical_memory" });
  if (!d.allow) {
    return snapshot(day, {
      agentDegraded: false,
      ingestionInProgress: false,
      controlPlane: "unconfigured",
      agentServiceHealth: "unconfigured",
    });
  }
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return snapshot(day, {
      agentDegraded: false,
      ingestionInProgress: false,
      controlPlane: "unconfigured",
      agentServiceHealth: "unconfigured",
    });
  }

  const oracleUrl = process.env.DEPLOYAI_ORACLE_HEALTH_URL?.trim();
  const [healthzOk, oracleRes] = await Promise.all([
    fetchControlPlaneHealthzOk(base),
    fetchOptionalOracleServiceHealth(oracleUrl || undefined),
  ]);
  const agentHealth: AgentServiceHealth =
    oracleRes === null ? "unconfigured" : oracleRes ? "ok" : "error";
  const agentDegradedFromOracle = oracleRes !== null && !oracleRes;

  if (!healthzOk) {
    return snapshot(day, {
      agentDegraded: true,
      ingestionInProgress: false,
      controlPlane: "error",
      agentServiceHealth: agentHealth,
    });
  }

  const url = `${base.replace(/\/$/, "")}/internal/v1/ingestion-runs?limit=200`;
  try {
    const r = await fetch(url, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
    });
    if (!r.ok) {
      return snapshot(day, {
        agentDegraded: true,
        ingestionInProgress: false,
        controlPlane: "error",
        agentServiceHealth: agentHealth,
      });
    }
    const runs = (await r.json()) as CpIngestionRun[];
    if (!Array.isArray(runs)) {
      return snapshot(day, {
        agentDegraded: true,
        ingestionInProgress: false,
        controlPlane: "error",
        agentServiceHealth: agentHealth,
      });
    }
    const tid = actor.tenantId?.trim() ?? null;
    const scoped = tid ? runs.filter((x) => x.tenant_id === tid) : [];
    const running = scoped.filter((x) => x.status === "running");
    return snapshot(day, {
      agentDegraded: agentDegradedFromOracle,
      ingestionInProgress: running.length > 0,
      controlPlane: "ok",
      agentServiceHealth: agentHealth,
    });
  } catch {
    return snapshot(day, {
      agentDegraded: true,
      ingestionInProgress: false,
      controlPlane: "error",
      agentServiceHealth: agentHealth,
    });
  }
}
