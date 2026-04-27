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

const IDLE_MEETING = {
  inMeeting: false,
  meetingId: null as string | null,
  meetingTitle: null as string | null,
  oracleInMeetingAlertAt: null as string | null,
  meetingDetectionSource: null as string | null,
  calendarPollIntervalSeconds: null as number | null,
};

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
  /** Epic 9.1 — Graph calendar wiring deferred; values come from CP stub or URL demo merge. */
  inMeeting: boolean;
  meetingId: string | null;
  meetingTitle: string | null;
  oracleInMeetingAlertAt: string | null;
  /** From CP `meeting-presence` (`detection_source`) or URL demo merge. */
  meetingDetectionSource: string | null;
  /** CP-suggested poll cadence for calendar/presence (seconds, 5–30). */
  calendarPollIntervalSeconds: number | null;
};

type ActivityWithoutDate = Omit<StrategistActivitySnapshot, "strategistLocalDate">;

function snapshot(
  day: string,
  partial: Partial<ActivityWithoutDate> &
    Pick<
      StrategistActivitySnapshot,
      "agentDegraded" | "ingestionInProgress" | "controlPlane" | "agentServiceHealth"
    >,
): StrategistActivitySnapshot {
  return { strategistLocalDate: day, ...IDLE_MEETING, ...partial };
}

function clampPollSeconds(n: unknown): number | null {
  if (typeof n !== "number" || !Number.isFinite(n)) {
    return null;
  }
  const r = Math.round(n);
  return Math.min(30, Math.max(5, r));
}

function parseMeetingPresenceJson(
  body: unknown,
): Pick<
  StrategistActivitySnapshot,
  | "inMeeting"
  | "meetingId"
  | "meetingTitle"
  | "oracleInMeetingAlertAt"
  | "meetingDetectionSource"
  | "calendarPollIntervalSeconds"
> {
  if (!body || typeof body !== "object") {
    return IDLE_MEETING;
  }
  const j = body as Record<string, unknown>;
  const src = j.detection_source;
  return {
    inMeeting: Boolean(j.in_meeting),
    meetingId: typeof j.meeting_id === "string" ? j.meeting_id : null,
    meetingTitle: typeof j.meeting_title === "string" ? j.meeting_title : null,
    oracleInMeetingAlertAt:
      typeof j.oracle_in_meeting_alert_at === "string" ? j.oracle_in_meeting_alert_at : null,
    meetingDetectionSource: typeof src === "string" && src.length > 0 ? src : null,
    calendarPollIntervalSeconds: clampPollSeconds(j.calendar_poll_interval_seconds),
  };
}

async function fetchMeetingPresence(
  base: string,
  key: string,
  tenantId: string | null,
): Promise<
  Pick<
    StrategistActivitySnapshot,
    | "inMeeting"
    | "meetingId"
    | "meetingTitle"
    | "oracleInMeetingAlertAt"
    | "meetingDetectionSource"
    | "calendarPollIntervalSeconds"
  >
> {
  if (!tenantId) {
    return IDLE_MEETING;
  }
  try {
    const u = `${base.replace(/\/$/, "")}/internal/v1/strategist/meeting-presence?tenant_id=${encodeURIComponent(tenantId)}`;
    const r = await fetch(u, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
    });
    if (!r.ok) {
      return IDLE_MEETING;
    }
    return parseMeetingPresenceJson(await r.json());
  } catch {
    return IDLE_MEETING;
  }
}

/**
 * Health + running-ingest for strategist chrome (FR46/FR47).
 * - Liveness: `GET {controlPlane}/healthz` before internal APIs.
 * - Ingest: `GET /internal/v1/ingestion-runs` (tenant-scoped; **no** tenant id ⇒ no running rows / FR47).
 * - Optional agents: `GET DEPLOYAI_ORACLE_HEALTH_URL` when set.
 * - Epic 9.1: `GET /internal/v1/strategist/meeting-presence` (active-meeting signal). Microsoft Graph
 *   calendar polling is deferred; CP may stub tenants via `DEPLOYAI_STUB_IN_MEETING_TENANT_IDS`.
 *   Browser demo flags (`?inMeeting=1`, …) merge in `StrategistShell` after this snapshot.
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

  const tid = actor.tenantId?.trim() ?? null;
  const ingestUrl = `${base.replace(/\/$/, "")}/internal/v1/ingestion-runs?limit=200`;

  try {
    const [r, meetingPart] = await Promise.all([
      fetch(ingestUrl, {
        headers: { "X-DeployAI-Internal-Key": key },
        cache: "no-store",
      }),
      fetchMeetingPresence(base, key, tid),
    ]);
    if (!r.ok) {
      return snapshot(day, {
        agentDegraded: true,
        ingestionInProgress: false,
        controlPlane: "error",
        agentServiceHealth: agentHealth,
        ...meetingPart,
      });
    }
    const runs = (await r.json()) as CpIngestionRun[];
    if (!Array.isArray(runs)) {
      return snapshot(day, {
        agentDegraded: true,
        ingestionInProgress: false,
        controlPlane: "error",
        agentServiceHealth: agentHealth,
        ...meetingPart,
      });
    }
    const scoped = tid ? runs.filter((x) => x.tenant_id === tid) : [];
    const running = scoped.filter((x) => x.status === "running");
    return snapshot(day, {
      agentDegraded: agentDegradedFromOracle,
      ingestionInProgress: running.length > 0,
      controlPlane: "ok",
      agentServiceHealth: agentHealth,
      ...meetingPart,
    });
  } catch {
    return snapshot(day, {
      agentDegraded: true,
      ingestionInProgress: false,
      controlPlane: "error",
      agentServiceHealth: agentHealth,
      ...IDLE_MEETING,
    });
  }
}
