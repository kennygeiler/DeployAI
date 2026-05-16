/**
 * Authoritative strategist surface DTO shapes (digest, phase, evening).
 * No fixture data — types only for CP / HTTP payloads and validation.
 */
import type {
  CitationPreview,
  EvidencePanelMetadata,
  EvidencePanelState,
} from "@deployai/shared-ui";
import type { EvidenceSpan, RetrievalPhase } from "@deployai/contracts";

export type DigestTopItem = {
  id: string;
  label: string;
  preview: CitationPreview;
  retrievalPhase: RetrievalPhase;
  metadata: EvidencePanelMetadata;
  state: EvidencePanelState;
  bodyText: string;
  evidenceSpan: EvidenceSpan;
};

export type EveningPatternRow = { id: string; title: string; note: string };

export type ActionQueueRow = {
  id: string;
  title: string;
  phase: string;
  status: "open" | "in_progress" | "blocked";
  assignee: string;
  due: string;
  priority: number;
  summary: string;
  retrievalPhase: RetrievalPhase;
  metadata: EvidencePanelMetadata;
  bodyText: string;
  evidenceSpan: EvidenceSpan;
};

export type DueDateWindow = "all" | "today" | "next7" | "overdue";

/** Optional “ranked out” lines when the control plane supplies them (no local fixtures). */
export type DigestRankedOutItem = { id: string; label: string; reason: string };
