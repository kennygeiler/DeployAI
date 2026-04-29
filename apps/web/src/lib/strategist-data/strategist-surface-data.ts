import type { CitationPreview } from "@deployai/shared-ui";
import type { EvidencePanelMetadata, EvidencePanelState } from "@deployai/shared-ui";
import type { EvidenceSpan } from "@deployai/contracts";

import type { AuthActor } from "@deployai/authz";

import type { ActionQueueRow, DigestTopItem, EveningPatternRow } from "@/lib/epic8/mock-digest";
import {
  buildPhaseTrackingRows,
  EVENING_CANDIDATES,
  MORNING_DIGEST_TOP,
  getStrategistEvidenceByNodeId,
} from "@/lib/epic8/mock-digest";
import { getControlPlaneBaseUrl, getControlPlaneInternalKey } from "@/lib/internal/control-plane";
import {
  digestSurfacesUseControlPlane,
  eveningSynthesisSurfacesUseControlPlane,
  evidenceSurfacesUseControlPlane,
  phaseTrackingSurfacesUseControlPlane,
} from "@/lib/internal/strategist-pilot-tenant";

const STRATEGIST_REMOTE_FETCH_TIMEOUT_MS = 8000;

const ISO_DUE_DATE = /^\d{4}-\d{2}-\d{2}$/;

const ACTION_QUEUE_STATUSES: ReadonlySet<ActionQueueRow["status"]> = new Set([
  "open",
  "in_progress",
  "blocked",
]);

const EVIDENCE_STATES: ReadonlySet<EvidencePanelState> = new Set([
  "loading",
  "loaded",
  "degraded",
  "tombstoned",
]);

const SUPERSESSION_LABELS: ReadonlySet<EvidencePanelMetadata["supersession"]> = new Set([
  "current",
  "superseded",
  "unknown",
  "tombstoned",
]);

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === "object" && x !== null && !Array.isArray(x);
}

function isCitationPreview(x: unknown): x is CitationPreview {
  if (!isRecord(x)) return false;
  return (
    typeof x.citationId === "string" &&
    typeof x.retrievalPhase === "string" &&
    typeof x.confidence === "string" &&
    typeof x.signedTimestamp === "string"
  );
}

function isEvidencePanelMetadata(x: unknown): x is EvidencePanelMetadata {
  if (!isRecord(x)) return false;
  if (
    typeof x.sourceType !== "string" ||
    typeof x.timestamp !== "string" ||
    typeof x.phase !== "string" ||
    typeof x.confidence !== "string" ||
    typeof x.supersession !== "string"
  ) {
    return false;
  }
  if (!SUPERSESSION_LABELS.has(x.supersession as EvidencePanelMetadata["supersession"])) {
    return false;
  }
  if (x.supersessionDetail !== undefined && typeof x.supersessionDetail !== "string") {
    return false;
  }
  return true;
}

function isEvidenceSpan(x: unknown): x is EvidenceSpan {
  if (!isRecord(x)) return false;
  return (
    typeof x.start === "number" &&
    typeof x.end === "number" &&
    typeof x.source_ref === "string" &&
    Number.isFinite(x.start) &&
    Number.isFinite(x.end)
  );
}

function isDigestTopItem(x: unknown): x is DigestTopItem {
  if (!isRecord(x)) return false;
  if (typeof x.id !== "string" || typeof x.label !== "string" || typeof x.bodyText !== "string") {
    return false;
  }
  if (typeof x.retrievalPhase !== "string" || typeof x.state !== "string") {
    return false;
  }
  if (!EVIDENCE_STATES.has(x.state as EvidencePanelState)) {
    return false;
  }
  if (!isCitationPreview(x.preview)) return false;
  if (!isEvidencePanelMetadata(x.metadata)) return false;
  if (!isEvidenceSpan(x.evidenceSpan)) return false;
  // `RetrievalPhase` is a string union in contracts; accept any non-empty string from JSON.
  if ((x.retrievalPhase as string).length === 0) return false;
  return true;
}

function isEveningPatternRow(x: unknown): x is EveningPatternRow {
  if (!isRecord(x)) return false;
  return typeof x.id === "string" && typeof x.title === "string" && typeof x.note === "string";
}

function isActionQueueRow(x: unknown): x is ActionQueueRow {
  if (!isRecord(x)) return false;
  if (
    typeof x.id !== "string" ||
    typeof x.title !== "string" ||
    typeof x.phase !== "string" ||
    typeof x.status !== "string" ||
    typeof x.assignee !== "string" ||
    typeof x.due !== "string" ||
    typeof x.summary !== "string" ||
    typeof x.bodyText !== "string"
  ) {
    return false;
  }
  if (!ISO_DUE_DATE.test(x.due)) return false;
  if (!ACTION_QUEUE_STATUSES.has(x.status as ActionQueueRow["status"])) return false;
  if (typeof x.priority !== "number" || !Number.isFinite(x.priority)) return false;
  if (typeof x.retrievalPhase !== "string" || x.retrievalPhase.length === 0) return false;
  if (!isEvidencePanelMetadata(x.metadata)) return false;
  if (!isEvidenceSpan(x.evidenceSpan)) return false;
  return true;
}

export function parseDigestTopItemsPayload(json: unknown): readonly DigestTopItem[] | null {
  if (!Array.isArray(json) || json.length === 0) {
    return null;
  }
  const out: DigestTopItem[] = [];
  for (const row of json) {
    if (!isDigestTopItem(row)) {
      return null;
    }
    out.push(row);
  }
  return out;
}

/** Single-object `DigestTopItem` (e.g. CP evidence-node payload). */
export function parseDigestTopItemSingle(json: unknown): DigestTopItem | null {
  if (!isDigestTopItem(json)) {
    return null;
  }
  return json;
}

/**
 * Remote evening payload: digest-shaped candidate cards + cross-account pattern rows.
 * `candidates` must be a non-empty array of valid `DigestTopItem` rows.
 * `patterns` is optional; when omitted, treated as empty (valid).
 */
export function parseEveningSynthesisPayload(json: unknown): {
  candidates: readonly DigestTopItem[];
  patterns: readonly EveningPatternRow[];
} | null {
  if (!isRecord(json)) return null;
  const candJson = json.candidates;
  if (!Array.isArray(candJson)) return null;
  const candidates = parseDigestTopItemsPayload(candJson);
  if (!candidates) return null;
  const p = json.patterns;
  if (p !== undefined && !Array.isArray(p)) return null;
  const patternsRaw: unknown[] = p === undefined ? [] : p;
  const patterns: EveningPatternRow[] = [];
  for (const row of patternsRaw) {
    if (!isEveningPatternRow(row)) {
      return null;
    }
    patterns.push(row);
  }
  return { candidates, patterns };
}

export function parsePhaseTrackingRowsPayload(json: unknown): readonly ActionQueueRow[] | null {
  if (!Array.isArray(json) || json.length === 0) {
    return null;
  }
  const out: ActionQueueRow[] = [];
  for (const row of json) {
    if (!isActionQueueRow(row)) {
      return null;
    }
    out.push(row);
  }
  return out;
}

export type MorningDigestLoadSource = "mock" | "live" | "degraded";

export type MorningDigestDegradedReason =
  | "fetch_error"
  | "http_error"
  | "invalid_payload"
  | "empty_array"
  | "tenant_required"
  | "cp_not_configured"
  | "cp_unconfigured";

export type MorningDigestLoadResult = {
  readonly items: readonly DigestTopItem[];
  readonly source: MorningDigestLoadSource;
  readonly degradedReason?: MorningDigestDegradedReason;
  /** HTTP status when `degradedReason` is `http_error`. */
  readonly httpStatus?: number;
};

/**
 * Epic 16.4 — when `DEPLOYAI_DIGEST_SOURCE=cp` or the signed-in tenant matches
 * `DEPLOYAI_PILOT_TENANT_ID`, loads from CP pilot surface; otherwise delegates to
 * `loadMorningDigestTopItemsResult` (URL or mock).
 */
export async function loadMorningDigestTopItemsResultForActor(
  actor: AuthActor | null,
): Promise<MorningDigestLoadResult> {
  if (digestSurfacesUseControlPlane(actor)) {
    return loadMorningDigestFromControlPlane(actor);
  }
  return loadMorningDigestTopItemsResult();
}

async function loadMorningDigestFromControlPlane(
  actor: AuthActor | null,
): Promise<MorningDigestLoadResult> {
  const tid = actor?.tenantId?.trim();
  if (!tid) {
    return {
      items: MORNING_DIGEST_TOP,
      source: "degraded",
      degradedReason: "tenant_required",
    };
  }
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return {
      items: MORNING_DIGEST_TOP,
      source: "degraded",
      degradedReason: "cp_unconfigured",
    };
  }
  const u = `${base.replace(/\/$/, "")}/internal/v1/strategist/pilot-surfaces/morning-digest-top?tenant_id=${encodeURIComponent(tid)}`;
  try {
    const r = await fetch(u, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (r.status === 404) {
      return { items: [], source: "degraded", degradedReason: "cp_not_configured" };
    }
    if (!r.ok) {
      return {
        items: MORNING_DIGEST_TOP,
        source: "degraded",
        degradedReason: "http_error",
        httpStatus: r.status,
      };
    }
    const body = (await r.json()) as { items?: unknown };
    const rawItems = body.items;
    if (!Array.isArray(rawItems)) {
      return { items: MORNING_DIGEST_TOP, source: "degraded", degradedReason: "invalid_payload" };
    }
    if (rawItems.length === 0) {
      return { items: [], source: "live" };
    }
    const parsed = parseDigestTopItemsPayload(rawItems);
    if (!parsed) {
      return { items: MORNING_DIGEST_TOP, source: "degraded", degradedReason: "invalid_payload" };
    }
    return { items: parsed, source: "live" };
  } catch {
    return { items: MORNING_DIGEST_TOP, source: "degraded", degradedReason: "fetch_error" };
  }
}

/**
 * Optional remote source for the Morning Digest list (JSON array of `DigestTopItem` rows).
 * When `STRATEGIST_DIGEST_SOURCE_URL` is unset, returns seeded mock data (`source: mock`).
 * When set, fetches and validates the body; on any failure returns mock items with `source: degraded`
 * so the UI can show an honest banner (never silent fallback).
 */
export async function loadMorningDigestTopItemsResult(): Promise<MorningDigestLoadResult> {
  const u = process.env.STRATEGIST_DIGEST_SOURCE_URL?.trim();
  if (!u) {
    return { items: MORNING_DIGEST_TOP, source: "mock" };
  }
  try {
    const r = await fetch(u, {
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (!r.ok) {
      return {
        items: MORNING_DIGEST_TOP,
        source: "degraded",
        degradedReason: "http_error",
        httpStatus: r.status,
      };
    }
    let body: unknown;
    try {
      body = await r.json();
    } catch {
      return { items: MORNING_DIGEST_TOP, source: "degraded", degradedReason: "invalid_payload" };
    }
    if (!Array.isArray(body) || body.length === 0) {
      return { items: MORNING_DIGEST_TOP, source: "degraded", degradedReason: "empty_array" };
    }
    const parsed = parseDigestTopItemsPayload(body);
    if (!parsed) {
      return { items: MORNING_DIGEST_TOP, source: "degraded", degradedReason: "invalid_payload" };
    }
    return { items: parsed, source: "live" };
  } catch {
    return { items: MORNING_DIGEST_TOP, source: "degraded", degradedReason: "fetch_error" };
  }
}

/** @deprecated Prefer `loadMorningDigestTopItemsResult` when provenance matters. */
export async function loadMorningDigestTopItems(): Promise<readonly DigestTopItem[]> {
  const r = await loadMorningDigestTopItemsResult();
  return r.items;
}

export function morningDigestBannerMessage(result: MorningDigestLoadResult): string | null {
  if (result.source !== "degraded" || !result.degradedReason) {
    return null;
  }
  switch (result.degradedReason) {
    case "fetch_error":
      return "Could not reach the configured digest feed in time. Showing seeded demo items.";
    case "http_error":
      return `Digest feed returned HTTP ${result.httpStatus ?? "error"}. Showing seeded demo items.`;
    case "invalid_payload":
      return "Digest feed returned data we could not validate as digest rows. Showing seeded demo items.";
    case "empty_array":
      return "Digest feed returned no rows. Showing seeded demo items.";
    case "tenant_required":
      return "Control-plane digest mode requires a tenant id (JWT tid or x-deployai-tenant). Showing seeded demo items.";
    case "cp_unconfigured":
      return "Control plane URL or internal API key is not configured for digest loading. Showing seeded demo items.";
    case "cp_not_configured":
      return "No pilot digest data for this tenant in the control plane yet (see DEPLOYAI_PILOT_SURFACE_DATA_PATH).";
    default:
      return "Digest feed is unavailable. Showing seeded demo items.";
  }
}

/**
 * Epic 16.5 — evidence deep-link: `DEPLOYAI_EVIDENCE_SOURCE=cp` or pilot tenant → CP pilot surface;
 * otherwise mock bridge.
 */
export async function loadStrategistEvidenceItemForActor(
  actor: AuthActor,
  nodeId: string,
): Promise<DigestTopItem | null> {
  if (!evidenceSurfacesUseControlPlane(actor)) {
    return getStrategistEvidenceByNodeId(nodeId);
  }
  const tid = actor.tenantId?.trim();
  if (!tid) {
    return null;
  }
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return null;
  }
  const u = `${base.replace(/\/$/, "")}/internal/v1/strategist/pilot-surfaces/evidence-node/${encodeURIComponent(nodeId)}?tenant_id=${encodeURIComponent(tid)}`;
  try {
    const r = await fetch(u, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (!r.ok) {
      return null;
    }
    const body: unknown = await r.json();
    return parseDigestTopItemSingle(body);
  } catch {
    return null;
  }
}

export type PhaseTrackingLoadSource = MorningDigestLoadSource;

export type PhaseTrackingDegradedReason = MorningDigestDegradedReason;

export type PhaseTrackingLoadResult = {
  readonly items: readonly ActionQueueRow[];
  readonly source: PhaseTrackingLoadSource;
  readonly degradedReason?: PhaseTrackingDegradedReason;
  readonly httpStatus?: number;
};

function phaseTrackingFallbackRows(today: string): readonly ActionQueueRow[] {
  return buildPhaseTrackingRows(today);
}

async function loadPhaseTrackingFromControlPlane(
  actor: AuthActor | null,
  today: string,
): Promise<PhaseTrackingLoadResult> {
  const fallback = phaseTrackingFallbackRows(today);
  const tid = actor?.tenantId?.trim();
  if (!tid) {
    return {
      items: fallback,
      source: "degraded",
      degradedReason: "tenant_required",
    };
  }
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return {
      items: fallback,
      source: "degraded",
      degradedReason: "cp_unconfigured",
    };
  }
  const u = `${base.replace(/\/$/, "")}/internal/v1/strategist/pilot-surfaces/phase-tracking?tenant_id=${encodeURIComponent(tid)}`;
  try {
    const r = await fetch(u, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (r.status === 404) {
      return { items: [], source: "degraded", degradedReason: "cp_not_configured" };
    }
    if (!r.ok) {
      return {
        items: fallback,
        source: "degraded",
        degradedReason: "http_error",
        httpStatus: r.status,
      };
    }
    const body = (await r.json()) as { items?: unknown };
    const rawItems = body.items;
    if (!Array.isArray(rawItems)) {
      return { items: fallback, source: "degraded", degradedReason: "invalid_payload" };
    }
    if (rawItems.length === 0) {
      return { items: [], source: "live" };
    }
    const parsed = parsePhaseTrackingRowsPayload(rawItems);
    if (!parsed) {
      return { items: fallback, source: "degraded", degradedReason: "invalid_payload" };
    }
    return { items: parsed, source: "live" };
  } catch {
    return { items: fallback, source: "degraded", degradedReason: "fetch_error" };
  }
}

/**
 * Pilot tenant (`DEPLOYAI_PILOT_TENANT_ID`) or `DEPLOYAI_PHASE_TRACKING_SOURCE=cp` → CP pilot surface file.
 */
export async function loadPhaseTrackingRowsResultForActor(
  actor: AuthActor | null,
  today: string,
): Promise<PhaseTrackingLoadResult> {
  if (phaseTrackingSurfacesUseControlPlane(actor)) {
    return loadPhaseTrackingFromControlPlane(actor, today);
  }
  return loadPhaseTrackingRowsResult(today);
}

/**
 * Optional remote JSON array of `ActionQueueRow` for `/phase-tracking`.
 * When `STRATEGIST_PHASE_TRACKING_SOURCE_URL` is unset, returns `buildPhaseTrackingRows(today)` (`source: mock`).
 */
export async function loadPhaseTrackingRowsResult(today: string): Promise<PhaseTrackingLoadResult> {
  const u = process.env.STRATEGIST_PHASE_TRACKING_SOURCE_URL?.trim();
  const fallback = phaseTrackingFallbackRows(today);
  if (!u) {
    return { items: fallback, source: "mock" };
  }
  try {
    const r = await fetch(u, {
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (!r.ok) {
      return {
        items: fallback,
        source: "degraded",
        degradedReason: "http_error",
        httpStatus: r.status,
      };
    }
    let body: unknown;
    try {
      body = await r.json();
    } catch {
      return { items: fallback, source: "degraded", degradedReason: "invalid_payload" };
    }
    if (!Array.isArray(body) || body.length === 0) {
      return { items: fallback, source: "degraded", degradedReason: "empty_array" };
    }
    const parsed = parsePhaseTrackingRowsPayload(body);
    if (!parsed) {
      return { items: fallback, source: "degraded", degradedReason: "invalid_payload" };
    }
    return { items: parsed, source: "live" };
  } catch {
    return { items: fallback, source: "degraded", degradedReason: "fetch_error" };
  }
}

export async function loadPhaseTrackingRows(today: string): Promise<readonly ActionQueueRow[]> {
  const r = await loadPhaseTrackingRowsResultForActor(null, today);
  return r.items;
}

export function phaseTrackingBannerMessage(result: PhaseTrackingLoadResult): string | null {
  if (result.source !== "degraded" || !result.degradedReason) {
    return null;
  }
  switch (result.degradedReason) {
    case "fetch_error":
      return "Could not reach the configured phase-tracking feed in time. Showing seeded demo rows.";
    case "http_error":
      return `Phase-tracking feed returned HTTP ${result.httpStatus ?? "error"}. Showing seeded demo rows.`;
    case "invalid_payload":
      return "Phase-tracking feed returned data we could not validate as action-queue rows. Showing seeded demo rows.";
    case "empty_array":
      return "Phase-tracking feed returned no rows. Showing seeded demo rows.";
    case "tenant_required":
      return "Control-plane phase tracking requires a tenant id (JWT tid or x-deployai-tenant). Showing seeded demo rows.";
    case "cp_unconfigured":
      return "Control plane URL or internal API key is not configured for phase-tracking loading. Showing seeded demo rows.";
    case "cp_not_configured":
      return "No pilot phase-tracking data for this tenant in the control plane yet (see DEPLOYAI_PILOT_SURFACE_DATA_PATH).";
    default:
      return "Phase-tracking feed is unavailable. Showing seeded demo rows.";
  }
}

export type EveningSynthesisLoadSource = MorningDigestLoadSource;

export type EveningSynthesisDegradedReason = MorningDigestDegradedReason;

export type EveningSynthesisLoadResult = {
  readonly candidates: readonly DigestTopItem[];
  readonly patterns: readonly EveningPatternRow[];
  readonly source: EveningSynthesisLoadSource;
  readonly degradedReason?: EveningSynthesisDegradedReason;
  readonly httpStatus?: number;
};

function eveningSynthesisFallback(): {
  candidates: readonly DigestTopItem[];
  patterns: readonly EveningPatternRow[];
} {
  return {
    candidates: MORNING_DIGEST_TOP.slice(0, 2),
    patterns: EVENING_CANDIDATES,
  };
}

async function loadEveningSynthesisFromControlPlane(
  actor: AuthActor | null,
): Promise<EveningSynthesisLoadResult> {
  const fallback = eveningSynthesisFallback();
  const tid = actor?.tenantId?.trim();
  if (!tid) {
    return {
      ...fallback,
      source: "degraded",
      degradedReason: "tenant_required",
    };
  }
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return {
      ...fallback,
      source: "degraded",
      degradedReason: "cp_unconfigured",
    };
  }
  const u = `${base.replace(/\/$/, "")}/internal/v1/strategist/pilot-surfaces/evening-synthesis?tenant_id=${encodeURIComponent(tid)}`;
  try {
    const r = await fetch(u, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (r.status === 404) {
      return {
        candidates: [],
        patterns: [],
        source: "degraded",
        degradedReason: "cp_not_configured",
      };
    }
    if (!r.ok) {
      return {
        ...fallback,
        source: "degraded",
        degradedReason: "http_error",
        httpStatus: r.status,
      };
    }
    let body: unknown;
    try {
      body = await r.json();
    } catch {
      return { ...fallback, source: "degraded", degradedReason: "invalid_payload" };
    }
    if (!isRecord(body)) {
      return { ...fallback, source: "degraded", degradedReason: "invalid_payload" };
    }
    const parsed = parseEveningSynthesisPayload(body);
    if (!parsed) {
      return { ...fallback, source: "degraded", degradedReason: "invalid_payload" };
    }
    return { ...parsed, source: "live" };
  } catch {
    return { ...fallback, source: "degraded", degradedReason: "fetch_error" };
  }
}

/**
 * Optional remote JSON object `{ candidates: DigestTopItem[], patterns?: EveningPatternRow[] }`.
 * When `STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL` is unset, returns seeded stand-ins (`source: mock`).
 */
export async function loadEveningSynthesisResult(): Promise<EveningSynthesisLoadResult> {
  const u = process.env.STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL?.trim();
  const fallback = eveningSynthesisFallback();
  if (!u) {
    return { ...fallback, source: "mock" };
  }
  try {
    const r = await fetch(u, {
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (!r.ok) {
      return {
        ...fallback,
        source: "degraded",
        degradedReason: "http_error",
        httpStatus: r.status,
      };
    }
    let body: unknown;
    try {
      body = await r.json();
    } catch {
      return { ...fallback, source: "degraded", degradedReason: "invalid_payload" };
    }
    if (!isRecord(body)) {
      return { ...fallback, source: "degraded", degradedReason: "invalid_payload" };
    }
    const parsed = parseEveningSynthesisPayload(body);
    if (!parsed) {
      return { ...fallback, source: "degraded", degradedReason: "invalid_payload" };
    }
    return { ...parsed, source: "live" };
  } catch {
    return { ...fallback, source: "degraded", degradedReason: "fetch_error" };
  }
}

/** Pilot tenant (`DEPLOYAI_PILOT_TENANT_ID`) or `DEPLOYAI_EVENING_SYNTHESIS_SOURCE=cp` → CP pilot surface file. */
export async function loadEveningSynthesisResultForActor(
  actor: AuthActor | null,
): Promise<EveningSynthesisLoadResult> {
  if (eveningSynthesisSurfacesUseControlPlane(actor)) {
    return loadEveningSynthesisFromControlPlane(actor);
  }
  return loadEveningSynthesisResult();
}

export async function loadEveningSynthesis(): Promise<{
  candidates: readonly DigestTopItem[];
  patterns: readonly EveningPatternRow[];
}> {
  const r = await loadEveningSynthesisResult();
  return { candidates: r.candidates, patterns: r.patterns };
}

export function eveningSynthesisBannerMessage(result: EveningSynthesisLoadResult): string | null {
  if (result.source !== "degraded" || !result.degradedReason) {
    return null;
  }
  switch (result.degradedReason) {
    case "fetch_error":
      return "Could not reach the configured evening synthesis feed in time. Showing seeded demo content.";
    case "http_error":
      return `Evening synthesis feed returned HTTP ${result.httpStatus ?? "error"}. Showing seeded demo content.`;
    case "invalid_payload":
      return "Evening synthesis feed returned data we could not validate. Showing seeded demo content.";
    case "empty_array":
      return "Evening synthesis feed returned no usable payload. Showing seeded demo content.";
    case "tenant_required":
      return "Control-plane evening synthesis requires a tenant id (JWT tid or x-deployai-tenant). Showing seeded demo content.";
    case "cp_unconfigured":
      return "Control plane URL or internal API key is not configured for evening synthesis loading. Showing seeded demo content.";
    case "cp_not_configured":
      return "No pilot evening synthesis data for this tenant in the control plane yet (see DEPLOYAI_PILOT_SURFACE_DATA_PATH).";
    default:
      return "Evening synthesis feed is unavailable. Showing seeded demo content.";
  }
}
