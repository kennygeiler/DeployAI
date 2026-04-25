import {
  CitationEnvelopeSchema,
  type CitationEnvelope,
  type RetrievalPhase,
} from "@deployai/contracts";
import type {
  CitationPreview,
  CitationVisualState,
  EvidencePanelMetadata,
  EvidencePanelState,
  SupersessionLabel,
} from "@deployai/shared-ui";

export type ParsedAdjudicationCitation = {
  preview: CitationPreview;
  retrievalPhase: RetrievalPhase;
  panelMetadata: EvidencePanelMetadata;
  bodyText: string;
  state: EvidencePanelState;
  visualState: CitationVisualState | undefined;
  chipLabel: string;
  degradedHint?: string;
  tombstoneMessage?: string;
  /** Highlight span when `bodyText` and envelope align (UTF-16 indices). */
  evidenceSpan: CitationEnvelope["evidence_span"];
};

function isSupersessionLabel(v: unknown): v is SupersessionLabel {
  return v === "current" || v === "superseded" || v === "unknown" || v === "tombstoned";
}

function isPanelState(v: unknown): v is EvidencePanelState {
  return v === "loading" || v === "loaded" || v === "degraded" || v === "tombstoned";
}

function parseOptionalVisualState(v: unknown): CitationVisualState | undefined {
  if (v === "overridden" || v === "tombstoned") {
    return v;
  }
  return undefined;
}

/**
 * When adjudication `meta` includes a v0.1.0 `citation_envelope` (NFR55), map it
 * to `CitationChip` + `EvidencePanel` props. Optional keys:
 * - `evidence_body` — quoted span text for the panel body
 * - `citation_label` — short chip label (never a raw UUID in UI)
 * - `citation_panel_state` / `citation_visual_state` — UI state overrides
 * - `citation_supersession` + `citation_supersession_detail` — memory lifecycle
 * - `citation_degraded_hint` / `citation_tombstone_message` — copy for special states
 */
export function parseAdjudicationCitation(
  raw: Record<string, unknown> | null | undefined,
): ParsedAdjudicationCitation | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }
  const envRaw = raw.citation_envelope;
  if (!envRaw || typeof envRaw !== "object") {
    return null;
  }
  const parsed = CitationEnvelopeSchema.safeParse(envRaw);
  if (!parsed.success) {
    return null;
  }
  const env = parsed.data;
  const supersession: SupersessionLabel = isSupersessionLabel(raw.citation_supersession)
    ? raw.citation_supersession
    : "current";
  const detail =
    typeof raw.citation_supersession_detail === "string" &&
    raw.citation_supersession_detail.length > 0
      ? raw.citation_supersession_detail
      : undefined;

  const panelMetadata: EvidencePanelMetadata = {
    sourceType: env.evidence_span.source_ref,
    timestamp: env.signed_timestamp,
    phase: `Graph epoch ${env.graph_epoch}`,
    confidence: String(env.confidence_score),
    supersession,
    supersessionDetail: detail,
  };

  const state: EvidencePanelState = isPanelState(raw.citation_panel_state)
    ? raw.citation_panel_state
    : "loaded";
  const visualState = parseOptionalVisualState(raw.citation_visual_state);
  const chipLabel =
    typeof raw.citation_label === "string" && raw.citation_label.trim().length > 0
      ? raw.citation_label.trim()
      : "Cited source";
  const bodyText = typeof raw.evidence_body === "string" ? raw.evidence_body : "";
  const degradedHint =
    typeof raw.citation_degraded_hint === "string" && raw.citation_degraded_hint.length > 0
      ? raw.citation_degraded_hint
      : undefined;
  const tombstoneMessage =
    typeof raw.citation_tombstone_message === "string" && raw.citation_tombstone_message.length > 0
      ? raw.citation_tombstone_message
      : undefined;

  const preview: CitationPreview = {
    citationId: String(env.node_id),
    retrievalPhase: env.retrieval_phase,
    confidence: String(env.confidence_score),
    signedTimestamp: env.signed_timestamp,
  };

  return {
    preview,
    retrievalPhase: env.retrieval_phase,
    panelMetadata,
    bodyText,
    state,
    visualState,
    chipLabel,
    degradedHint,
    tombstoneMessage,
    evidenceSpan: env.evidence_span,
  };
}
