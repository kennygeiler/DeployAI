import type { CitationPreview } from "@deployai/shared-ui";
import type { EvidencePanelMetadata, EvidencePanelState } from "@deployai/shared-ui";
import type { EvidenceSpan } from "@deployai/contracts";

import type { AuthActor } from "@deployai/authz";

import type {
  ActionQueueRow,
  DigestTopItem,
  EveningPatternRow,
} from "@/lib/strategist-data/strategist-surface-types";
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
 * `candidates` may be an empty array; every non-empty element must validate as `DigestTopItem`.
 * `patterns` is optional; when omitted, treated as empty (valid).
 */
export function parseEveningSynthesisPayload(json: unknown): {
  candidates: readonly DigestTopItem[];
  patterns: readonly EveningPatternRow[];
} | null {
  if (!isRecord(json)) return null;
  const candJson = json.candidates;
  if (!Array.isArray(candJson)) return null;
  let candidates: readonly DigestTopItem[] = [];
  if (candJson.length > 0) {
    const parsed = parseDigestTopItemsPayload(candJson);
    if (!parsed) return null;
    candidates = parsed;
  }
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

export type MorningDigestLoadSource = "live" | "degraded";

export type MorningDigestDegradedReason =
  | "fetch_error"
  | "http_error"
  | "invalid_payload"
  | "empty_array"
  | "tenant_required"
  | "cp_not_configured"
  | "cp_unconfigured"
  | "no_configured_source";

export type MorningDigestLoadResult = {
  readonly items: readonly DigestTopItem[];
  readonly source: MorningDigestLoadSource;
  /** False when the payload is empty or degraded — never trust it as canonical telemetry. */
  readonly dataTrusted: boolean;
  readonly degradedReason?: MorningDigestDegradedReason;
  /** HTTP status when `degradedReason` is `http_error`. */
  readonly httpStatus?: number;
};

function digestEmptyDegraded(
  reason: MorningDigestDegradedReason,
  httpStatus?: number,
): MorningDigestLoadResult {
  return {
    items: [],
    source: "degraded",
    dataTrusted: false,
    degradedReason: reason,
    httpStatus,
  };
}

function digestLive(items: readonly DigestTopItem[]): MorningDigestLoadResult {
  return {
    items,
    source: "live",
    dataTrusted: true,
  };
}

/**
 * Epic 16.4 — when `DEPLOYAI_DIGEST_SOURCE=cp` or the signed-in tenant matches
 * `DEPLOYAI_PILOT_TENANT_ID`, loads from CP pilot surface; otherwise uses
 * `STRATEGIST_DIGEST_SOURCE_URL` when set. No file-backed fixtures.
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
    return digestEmptyDegraded("tenant_required");
  }
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return digestEmptyDegraded("cp_unconfigured");
  }
  const u = `${base.replace(/\/$/, "")}/internal/v1/strategist/pilot-surfaces/morning-digest-top?tenant_id=${encodeURIComponent(tid)}`;
  try {
    const r = await fetch(u, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (r.status === 404) {
      return digestEmptyDegraded("cp_not_configured");
    }
    if (!r.ok) {
      return digestEmptyDegraded("http_error", r.status);
    }
    const body = (await r.json()) as { items?: unknown };
    const rawItems = body.items;
    if (!Array.isArray(rawItems)) {
      return digestEmptyDegraded("invalid_payload");
    }
    if (rawItems.length === 0) {
      return digestLive([]);
    }
    const parsed = parseDigestTopItemsPayload(rawItems);
    if (!parsed) {
      return digestEmptyDegraded("invalid_payload");
    }
    return digestLive(parsed);
  } catch {
    return digestEmptyDegraded("fetch_error");
  }
}

/**
 * Optional remote source for the Morning Digest list (JSON array of `DigestTopItem` rows).
 * When `STRATEGIST_DIGEST_SOURCE_URL` is unset, returns an empty list with `dataTrusted: false`.
 */
export async function loadMorningDigestTopItemsResult(): Promise<MorningDigestLoadResult> {
  const u = process.env.STRATEGIST_DIGEST_SOURCE_URL?.trim();
  if (!u) {
    return digestEmptyDegraded("no_configured_source");
  }
  try {
    const r = await fetch(u, {
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (!r.ok) {
      return digestEmptyDegraded("http_error", r.status);
    }
    let body: unknown;
    try {
      body = await r.json();
    } catch {
      return digestEmptyDegraded("invalid_payload");
    }
    if (!Array.isArray(body) || body.length === 0) {
      return digestEmptyDegraded("empty_array");
    }
    const parsed = parseDigestTopItemsPayload(body);
    if (!parsed) {
      return digestEmptyDegraded("invalid_payload");
    }
    return digestLive(parsed);
  } catch {
    return digestEmptyDegraded("fetch_error");
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
      return "Could not reach the configured digest feed in time. Showing no rows (data not trusted).";
    case "http_error":
      return `Digest feed returned HTTP ${result.httpStatus ?? "error"}. Data not trusted — empty digest.`;
    case "invalid_payload":
      return "Digest feed returned data we could not validate as digest rows. Data not trusted — empty digest.";
    case "empty_array":
      return "Digest feed returned no rows. Data not trusted — empty digest.";
    case "tenant_required":
      return "Control-plane digest mode requires a tenant id (JWT tid or x-deployai-tenant). Data not trusted — empty digest.";
    case "cp_unconfigured":
      return "Control plane URL or internal API key is not configured for digest loading. Data not trusted — empty digest.";
    case "cp_not_configured":
      return "No pilot digest data for this tenant in the control plane yet (see DEPLOYAI_PILOT_SURFACE_DATA_PATH).";
    case "no_configured_source":
      return "No digest feed is configured (set STRATEGIST_DIGEST_SOURCE_URL or pilot/CP digest mode). Data not trusted — empty digest.";
    default:
      return "Digest feed is unavailable. Data not trusted — empty digest.";
  }
}

/** P5 — `/evidence/[nodeId]` resolution against tenant-scoped pilot surface (Epic 16.5). */
export type StrategistEvidenceLoadResult =
  | { readonly status: "ok"; readonly item: DigestTopItem }
  | { readonly status: "not_found" }
  /** CP evidence requested but URL/key missing — treated like missing page in SSR today. */
  | { readonly status: "cp_unconfigured" };

function evidenceNodeIdsMatch(requestedNodeId: string, payloadNodeId: string): boolean {
  const a = requestedNodeId.trim();
  const b = payloadNodeId.trim();
  if (a === b) {
    return true;
  }
  return a.toLowerCase() === b.toLowerCase();
}

async function fetchEvidenceDigestTopFromPilotSurface(
  tenantId: string,
  requestedNodeId: string,
): Promise<StrategistEvidenceLoadResult> {
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return { status: "cp_unconfigured" };
  }
  const u = `${base.replace(/\/$/, "")}/internal/v1/strategist/pilot-surfaces/evidence-node/${encodeURIComponent(requestedNodeId)}?tenant_id=${encodeURIComponent(tenantId)}`;
  try {
    const r = await fetch(u, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (r.status === 404) {
      return { status: "not_found" };
    }
    if (!r.ok) {
      return { status: "not_found" };
    }
    const body: unknown = await r.json();
    const parsed = parseDigestTopItemSingle(body);
    if (!parsed || !evidenceNodeIdsMatch(requestedNodeId, parsed.id)) {
      return { status: "not_found" };
    }
    return { status: "ok", item: parsed };
  } catch {
    return { status: "not_found" };
  }
}

/**
 * Epic 16.5 / P5 — tenant + `canonical:read` must be enforced by the page (`requireCanonicalRead`) before calling.
 * CP path uses tenant-scoped pilot surface; missing node or wrong tenant → `not_found` (matches CP 404).
 * Without CP evidence mode, returns `not_found` (file-backed evidence fixtures removed).
 */
export async function resolveStrategistEvidenceForActor(
  actor: AuthActor,
  nodeId: string,
): Promise<StrategistEvidenceLoadResult> {
  if (!evidenceSurfacesUseControlPlane(actor)) {
    return { status: "not_found" };
  }
  const tid = actor.tenantId?.trim();
  if (!tid) {
    return { status: "not_found" };
  }
  return fetchEvidenceDigestTopFromPilotSurface(tid, nodeId);
}

/**
 * Epic 16.5 — evidence deep-link: `DEPLOYAI_EVIDENCE_SOURCE=cp` or pilot tenant → CP pilot surface.
 */
export async function loadStrategistEvidenceItemForActor(
  actor: AuthActor,
  nodeId: string,
): Promise<DigestTopItem | null> {
  const r = await resolveStrategistEvidenceForActor(actor, nodeId);
  if (r.status === "ok") {
    return r.item;
  }
  return null;
}

export type PhaseTrackingLoadSource = MorningDigestLoadSource;

export type PhaseTrackingDegradedReason = MorningDigestDegradedReason;

export type PhaseTrackingLoadResult = {
  readonly items: readonly ActionQueueRow[];
  readonly source: PhaseTrackingLoadSource;
  readonly dataTrusted: boolean;
  readonly degradedReason?: PhaseTrackingDegradedReason;
  readonly httpStatus?: number;
};

function phaseEmptyDegraded(
  reason: PhaseTrackingDegradedReason,
  httpStatus?: number,
): PhaseTrackingLoadResult {
  return {
    items: [],
    source: "degraded",
    dataTrusted: false,
    degradedReason: reason,
    httpStatus,
  };
}

function phaseLive(items: readonly ActionQueueRow[]): PhaseTrackingLoadResult {
  return {
    items,
    source: "live",
    dataTrusted: true,
  };
}

async function loadPhaseTrackingFromControlPlane(
  actor: AuthActor | null,
): Promise<PhaseTrackingLoadResult> {
  const tid = actor?.tenantId?.trim();
  if (!tid) {
    return phaseEmptyDegraded("tenant_required");
  }
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return phaseEmptyDegraded("cp_unconfigured");
  }
  const u = `${base.replace(/\/$/, "")}/internal/v1/strategist/pilot-surfaces/phase-tracking?tenant_id=${encodeURIComponent(tid)}`;
  try {
    const r = await fetch(u, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (r.status === 404) {
      return phaseEmptyDegraded("cp_not_configured");
    }
    if (!r.ok) {
      return phaseEmptyDegraded("http_error", r.status);
    }
    const body = (await r.json()) as { items?: unknown };
    const rawItems = body.items;
    if (!Array.isArray(rawItems)) {
      return phaseEmptyDegraded("invalid_payload");
    }
    if (rawItems.length === 0) {
      return phaseLive([]);
    }
    const parsed = parsePhaseTrackingRowsPayload(rawItems);
    if (!parsed) {
      return phaseEmptyDegraded("invalid_payload");
    }
    return phaseLive(parsed);
  } catch {
    return phaseEmptyDegraded("fetch_error");
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
    return loadPhaseTrackingFromControlPlane(actor);
  }
  return loadPhaseTrackingRowsResult(today);
}

/**
 * Optional remote JSON array of `ActionQueueRow` for `/phase-tracking`.
 * When `STRATEGIST_PHASE_TRACKING_SOURCE_URL` is unset, returns an empty list with `dataTrusted: false`.
 */
export async function loadPhaseTrackingRowsResult(
  _today: string,
): Promise<PhaseTrackingLoadResult> {
  void _today;
  const u = process.env.STRATEGIST_PHASE_TRACKING_SOURCE_URL?.trim();
  if (!u) {
    return phaseEmptyDegraded("no_configured_source");
  }
  try {
    const r = await fetch(u, {
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (!r.ok) {
      return phaseEmptyDegraded("http_error", r.status);
    }
    let body: unknown;
    try {
      body = await r.json();
    } catch {
      return phaseEmptyDegraded("invalid_payload");
    }
    if (!Array.isArray(body) || body.length === 0) {
      return phaseEmptyDegraded("empty_array");
    }
    const parsed = parsePhaseTrackingRowsPayload(body);
    if (!parsed) {
      return phaseEmptyDegraded("invalid_payload");
    }
    return phaseLive(parsed);
  } catch {
    return phaseEmptyDegraded("fetch_error");
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
      return "Could not reach the configured phase-tracking feed in time. Data not trusted — empty table.";
    case "http_error":
      return `Phase-tracking feed returned HTTP ${result.httpStatus ?? "error"}. Data not trusted — empty table.`;
    case "invalid_payload":
      return "Phase-tracking feed returned data we could not validate as action-queue rows. Data not trusted — empty table.";
    case "empty_array":
      return "Phase-tracking feed returned no rows. Data not trusted — empty table.";
    case "tenant_required":
      return "Control-plane phase tracking requires a tenant id (JWT tid or x-deployai-tenant). Data not trusted — empty table.";
    case "cp_unconfigured":
      return "Control plane URL or internal API key is not configured for phase-tracking loading. Data not trusted — empty table.";
    case "cp_not_configured":
      return "No pilot phase-tracking data for this tenant in the control plane yet (see DEPLOYAI_PILOT_SURFACE_DATA_PATH).";
    case "no_configured_source":
      return "No phase-tracking feed is configured (set STRATEGIST_PHASE_TRACKING_SOURCE_URL or pilot/CP mode). Data not trusted — empty table.";
    default:
      return "Phase-tracking feed is unavailable. Data not trusted — empty table.";
  }
}

export type EveningSynthesisLoadSource = MorningDigestLoadSource;

export type EveningSynthesisDegradedReason = MorningDigestDegradedReason;

export type EveningSynthesisLoadResult = {
  readonly candidates: readonly DigestTopItem[];
  readonly patterns: readonly EveningPatternRow[];
  readonly source: EveningSynthesisLoadSource;
  readonly dataTrusted: boolean;
  readonly degradedReason?: EveningSynthesisDegradedReason;
  readonly httpStatus?: number;
};

function eveningEmptyDegraded(
  reason: EveningSynthesisDegradedReason,
  httpStatus?: number,
): EveningSynthesisLoadResult {
  return {
    candidates: [],
    patterns: [],
    source: "degraded",
    dataTrusted: false,
    degradedReason: reason,
    httpStatus,
  };
}

function eveningLive(
  candidates: readonly DigestTopItem[],
  patterns: readonly EveningPatternRow[],
): EveningSynthesisLoadResult {
  return {
    candidates,
    patterns,
    source: "live",
    dataTrusted: true,
  };
}

async function loadEveningSynthesisFromControlPlane(
  actor: AuthActor | null,
): Promise<EveningSynthesisLoadResult> {
  const tid = actor?.tenantId?.trim();
  if (!tid) {
    return eveningEmptyDegraded("tenant_required");
  }
  const base = getControlPlaneBaseUrl();
  const key = getControlPlaneInternalKey();
  if (!base || !key) {
    return eveningEmptyDegraded("cp_unconfigured");
  }
  const u = `${base.replace(/\/$/, "")}/internal/v1/strategist/pilot-surfaces/evening-synthesis?tenant_id=${encodeURIComponent(tid)}`;
  try {
    const r = await fetch(u, {
      headers: { "X-DeployAI-Internal-Key": key },
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (r.status === 404) {
      return eveningEmptyDegraded("cp_not_configured");
    }
    if (!r.ok) {
      return eveningEmptyDegraded("http_error", r.status);
    }
    let body: unknown;
    try {
      body = await r.json();
    } catch {
      return eveningEmptyDegraded("invalid_payload");
    }
    if (!isRecord(body)) {
      return eveningEmptyDegraded("invalid_payload");
    }
    const parsed = parseEveningSynthesisPayload(body);
    if (!parsed) {
      return eveningEmptyDegraded("invalid_payload");
    }
    return eveningLive(parsed.candidates, parsed.patterns);
  } catch {
    return eveningEmptyDegraded("fetch_error");
  }
}

/**
 * Optional remote JSON object `{ candidates: DigestTopItem[], patterns?: EveningPatternRow[] }`.
 * When `STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL` is unset, returns empty candidates/patterns with `dataTrusted: false`.
 */
export async function loadEveningSynthesisResult(): Promise<EveningSynthesisLoadResult> {
  const u = process.env.STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL?.trim();
  if (!u) {
    return eveningEmptyDegraded("no_configured_source");
  }
  try {
    const r = await fetch(u, {
      cache: "no-store",
      signal: AbortSignal.timeout(STRATEGIST_REMOTE_FETCH_TIMEOUT_MS),
    });
    if (!r.ok) {
      return eveningEmptyDegraded("http_error", r.status);
    }
    let body: unknown;
    try {
      body = await r.json();
    } catch {
      return eveningEmptyDegraded("invalid_payload");
    }
    if (!isRecord(body)) {
      return eveningEmptyDegraded("invalid_payload");
    }
    const parsed = parseEveningSynthesisPayload(body);
    if (!parsed) {
      return eveningEmptyDegraded("invalid_payload");
    }
    return eveningLive(parsed.candidates, parsed.patterns);
  } catch {
    return eveningEmptyDegraded("fetch_error");
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
      return "Could not reach the configured evening synthesis feed in time. Data not trusted — empty surface.";
    case "http_error":
      return `Evening synthesis feed returned HTTP ${result.httpStatus ?? "error"}. Data not trusted — empty surface.`;
    case "invalid_payload":
      return "Evening synthesis feed returned data we could not validate. Data not trusted — empty surface.";
    case "empty_array":
      return "Evening synthesis feed returned no usable payload. Data not trusted — empty surface.";
    case "tenant_required":
      return "Control-plane evening synthesis requires a tenant id (JWT tid or x-deployai-tenant). Data not trusted — empty surface.";
    case "cp_unconfigured":
      return "Control plane URL or internal API key is not configured for evening synthesis loading. Data not trusted — empty surface.";
    case "cp_not_configured":
      return "No pilot evening synthesis data for this tenant in the control plane yet (see DEPLOYAI_PILOT_SURFACE_DATA_PATH).";
    case "no_configured_source":
      return "No evening synthesis feed is configured (set STRATEGIST_EVENING_SYNTHESIS_SOURCE_URL or pilot/CP mode). Data not trusted — empty surface.";
    default:
      return "Evening synthesis feed is unavailable. Data not trusted — empty surface.";
  }
}
