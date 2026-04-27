import type { CitationPreview } from "@deployai/shared-ui";
import type { EvidencePanelMetadata, EvidencePanelState } from "@deployai/shared-ui";
import type { EvidenceSpan } from "@deployai/contracts";

import type { ActionQueueRow, DigestTopItem } from "@/lib/epic8/mock-digest";
import { buildPhaseTrackingRows, MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";

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
  | "empty_array";

export type MorningDigestLoadResult = {
  readonly items: readonly DigestTopItem[];
  readonly source: MorningDigestLoadSource;
  readonly degradedReason?: MorningDigestDegradedReason;
  /** HTTP status when `degradedReason` is `http_error`. */
  readonly httpStatus?: number;
};

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
    default:
      return "Digest feed is unavailable. Showing seeded demo items.";
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
  const r = await loadPhaseTrackingRowsResult(today);
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
    default:
      return "Phase-tracking feed is unavailable. Showing seeded demo rows.";
  }
}
