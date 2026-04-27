import type {
  CitationPreview,
  EvidencePanelMetadata,
  EvidencePanelState,
} from "@deployai/shared-ui";
import type { EvidenceSpan, RetrievalPhase } from "@deployai/contracts";

import { getStrategistLocalDateForServer } from "@/lib/internal/strategist-local-date";

const span = (source_ref: string, t: [number, number]): EvidenceSpan => ({
  start: t[0],
  end: t[1],
  source_ref,
});

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

export const MORNING_DIGEST_TOP: readonly DigestTopItem[] = [
  {
    id: "2d4437ee-9336-441e-ab57-121b81ee57a4",
    label: "07:00 — Program risks (DOT comms)",
    preview: {
      citationId: "2d4437ee-9336-441e-ab57-121b81ee57a4",
      retrievalPhase: "P3 — Ecosystem map",
      confidence: "0.94 (high agreement)",
      signedTimestamp: "2026-04-23T12:00:00.000Z",
    },
    retrievalPhase: "oracle",
    metadata: {
      sourceType: "M365 / Teams",
      timestamp: "2026-04-23T12:00:00.000Z",
      phase: "P3 Ecosystem",
      confidence: "0.94",
      supersession: "current",
    },
    state: "loaded",
    bodyText:
      "Stated blockers: dependencies on the legacy billing API before pilot sign-off. Align with program office before Friday.",
    evidenceSpan: span("urn:deployai:evidence:dot-standup-0423#p1", [18, 58]),
  },
  {
    id: "3b1c9aa1-8f0e-4c2a-9d10-2f0e5c1a9b2d",
    label: "Stakeholder: procurement checkpoint",
    preview: {
      citationId: "3b1c9aa1-8f0e-4c2a-9d10-2f0e5c1a9b2d",
      retrievalPhase: "P4 — Design",
      confidence: "0.88 (medium agreement)",
      signedTimestamp: "2026-04-23T11:20:00.000Z",
    },
    retrievalPhase: "cartographer",
    metadata: {
      sourceType: "Email thread",
      timestamp: "2026-04-23T11:20:00.000Z",
      phase: "P4 Design",
      confidence: "0.88",
      supersession: "current",
    },
    state: "loaded",
    bodyText:
      "CRO asked for a single-page RFP summary. Legal wants clause references attached — expect follow-up by EOD.",
    evidenceSpan: span("urn:deployai:evidence:email-thread-rfp#slice1", [20, 44]),
  },
  {
    id: "7e8f1c22-0d1a-4b5c-8e9f-0a1b2c3d4e5f",
    label: "Field note — pilot site visit",
    preview: {
      citationId: "7e8f1c22-0d1a-4b5c-8e9f-0a1b2c3d4e5f",
      retrievalPhase: "P5 — Pilot",
      confidence: "0.91 (high agreement)",
      signedTimestamp: "2026-04-23T10:45:00.000Z",
    },
    retrievalPhase: "synthesis",
    metadata: {
      sourceType: "Ingest / notes",
      timestamp: "2026-04-23T10:45:00.000Z",
      phase: "P5 Pilot",
      confidence: "0.91",
      supersession: "current",
    },
    state: "loaded",
    bodyText:
      "On-site: training room network drops twice per session. IT ticket opened; not a blocker for dry run Tuesday.",
    evidenceSpan: span("urn:deployai:evidence:field-note-visit#n1", [32, 45]),
  },
];

/** Suppressed candidates (Oracle 6.4 “ranked out”) — not in the hard 3. */
export const MORNING_DIGEST_RANKED_OUT: readonly { id: string; label: string; reason: string }[] = [
  {
    id: "out-1",
    label: "Low-signal: generic status email",
    reason: "Below confidence floor for digest",
  },
  { id: "out-2", label: "Duplicate: same DOT thread (older)", reason: "Superseded by item 1" },
];

export type EveningPatternRow = { id: string; title: string; note: string };

export const EVENING_CANDIDATES: readonly EveningPatternRow[] = [
  {
    id: "e1",
    title: "Recurring: vendor latency on artifact uploads",
    note: "Cross-account: 2 tenants this week",
  },
  {
    id: "e2",
    title: "Class B review: pilot KPI wording",
    note: "Tie to solidification review when Epic 9 lands",
  },
];

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

/** Strategist-local “today” for mock due-date windows (Story 8.2 date-range chips). */
export const PHASE_TRACKING_MOCK_TODAY = "2026-04-24" as const;

export type DueDateWindow = "all" | "today" | "next7" | "overdue";

function addDaysToIsoDate(isoDate: string, days: number): string {
  const t = new Date(`${isoDate}T12:00:00.000Z`);
  t.setUTCDate(t.getUTCDate() + days);
  return t.toISOString().slice(0, 10);
}

/**
 * YYYY-MM-DD due cell vs window chips (string comparison is valid for ISO dates).
 * `next7` = today through today+6 (seven calendar days inclusive).
 */
export function actionQueueRowMatchesDueWindow(
  due: string,
  window: DueDateWindow,
  today: string = PHASE_TRACKING_MOCK_TODAY,
): boolean {
  if (window === "all") {
    return true;
  }
  if (window === "today") {
    return due === today;
  }
  if (window === "overdue") {
    return due < today;
  }
  const end = addDaysToIsoDate(today, 6);
  return due >= today && due <= end;
}

/**
 * Action-queue mock rows with due dates **relative** to strategist-local `today`
 * (tomorrow, today, +2, −4) so date-window chips always have a non-empty walkthrough.
 */
export function buildPhaseTrackingRows(today: string): ActionQueueRow[] {
  return [
    {
      id: "aq-1",
      title: "Confirm pilot exit criteria with sponsor",
      phase: "P5 Pilot",
      status: "in_progress",
      assignee: "You",
      due: addDaysToIsoDate(today, 1),
      priority: 1,
      summary: "Sponsor sign-off on success metrics before go-live date.",
      retrievalPhase: "oracle",
      metadata: {
        sourceType: "Action Queue",
        timestamp: "2026-04-22T16:00:00.000Z",
        phase: "P5 Pilot",
        confidence: "—",
        supersession: "current",
      },
      bodyText:
        "Exit criteria: 95% task completion, zero sev-1 in two consecutive weeks, training sign-off.",
      evidenceSpan: span("urn:deployai:evidence:action-aq-1#ex1", [15, 35]),
    },
    {
      id: "aq-2",
      title: "Resolve blockers: legacy API dependency",
      phase: "P4 Design",
      status: "blocked",
      assignee: "Unassigned",
      due: today,
      priority: 2,
      summary: "Same evidence as top digest item — block program office alignment.",
      retrievalPhase: "master_strategist",
      metadata: {
        sourceType: "Action Queue",
        timestamp: "2026-04-22T12:00:00.000Z",
        phase: "P4 Design",
        confidence: "—",
        supersession: "current",
      },
      bodyText: "Blocked on decision from enterprise architecture on sunset date.",
      evidenceSpan: span("urn:deployai:evidence:action-aq-2#ex1", [28, 52]),
    },
    {
      id: "aq-3",
      title: "Book dry run with field trainers",
      phase: "P5 Pilot",
      status: "open",
      assignee: "Field lead",
      due: addDaysToIsoDate(today, 2),
      priority: 3,
      summary: "One session; capture network and room layout issues.",
      retrievalPhase: "cartographer",
      metadata: {
        sourceType: "Action Queue",
        timestamp: "2026-04-21T09:00:00.000Z",
        phase: "P5 Pilot",
        confidence: "—",
        supersession: "current",
      },
      bodyText: "Dry run: Tuesday 10:00 local; Teams bridge for remote observers.",
      evidenceSpan: span("urn:deployai:evidence:action-aq-3#ex1", [8, 23]),
    },
    {
      id: "aq-4",
      title: "Confirm data residency language with security",
      phase: "P4 Design",
      status: "open",
      assignee: "Security",
      due: addDaysToIsoDate(today, -4),
      priority: 4,
      summary: "Blocker for pilot contract — due last week; escalate if no answer.",
      retrievalPhase: "master_strategist",
      metadata: {
        sourceType: "Action Queue",
        timestamp: "2026-04-20T14:00:00.000Z",
        phase: "P4 Design",
        confidence: "—",
        supersession: "current",
      },
      bodyText: "Residency: US-only store for pilot artifacts; legal needs the approved clause id.",
      evidenceSpan: span("urn:deployai:evidence:action-aq-4#ex1", [0, 24]),
    },
  ];
}

/** Fixed snapshot for unit tests (matches `PHASE_TRACKING_MOCK_TODAY` offsets). */
export const PHASE_TRACKING_ROWS: readonly ActionQueueRow[] = Object.freeze(
  buildPhaseTrackingRows(PHASE_TRACKING_MOCK_TODAY),
);

/**
 * Story 8.4 — resolve digest or action-queue rows for `/evidence/[nodeId]`.
 * Production will query canonical memory by `node_id`; this bridges mocks.
 */
export function getStrategistEvidenceByNodeId(nodeId: string): DigestTopItem | null {
  const d = MORNING_DIGEST_TOP.find((x) => x.id === nodeId);
  if (d) {
    return d;
  }
  const localDay = getStrategistLocalDateForServer();
  const aq = buildPhaseTrackingRows(localDay).find((r) => r.id === nodeId);
  if (!aq) {
    return null;
  }
  return {
    id: aq.id,
    label: aq.title,
    preview: {
      citationId: aq.id,
      retrievalPhase: `${aq.phase} (action)`,
      confidence: "—",
      signedTimestamp: aq.metadata.timestamp,
    },
    retrievalPhase: aq.retrievalPhase,
    metadata: aq.metadata,
    state: "loaded",
    bodyText: `${aq.summary}\n\n${aq.bodyText}`,
    evidenceSpan: aq.evidenceSpan,
  };
}
