import { z } from "zod";

/** Frozen semver for the citation envelope (Story 1.11, NFR55). */
export const CITATION_ENVELOPE_SCHEMA_VERSION = "0.1.0" as const;

/** Phases that may emit a citation (aligns with Cartographer / Oracle / MS / assembly). */
export const retrievalPhaseSchema = z.enum([
  "cartographer",
  "oracle",
  "master_strategist",
  "synthesis",
]);

export type RetrievalPhase = z.infer<typeof retrievalPhaseSchema>;

export const evidenceSpanSchema = z.object({
  start: z.number().int().nonnegative(),
  end: z.number().int().nonnegative(),
  source_ref: z.string().min(1),
});

export type EvidenceSpan = z.infer<typeof evidenceSpanSchema>;

/** Epic 10.3 — cite of a learning that was strategist-overridden. */
export const citationSupersessionOverriddenSchema = z.object({
  type: z.literal("overridden"),
  override_event_id: z.string().uuid(),
  overriding_evidence_event_ids: z.array(z.string().uuid()).min(1),
});

export type CitationSupersessionOverridden = z.infer<typeof citationSupersessionOverriddenSchema>;

/**
 * RFC 3339 timestamp pattern for `signed_timestamp`.
 * MUST stay byte-identical in sync with the Python validator regex at
 * `services/_shared/citation/src/deployai_citation/citation.py:23`
 * (`_is_rfc3339_utcish`) — cross-language drift on this field is exactly
 * what backlog ticket B6 reconciled. Shared valid/invalid fixture strings
 * are asserted in `tests/envelope.contract.test.ts` and
 * `services/_shared/citation/tests/test_citation.py`.
 */
export const SIGNED_TIMESTAMP_RFC3339_REGEX =
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

/**
 * Mandatory envelope for any agent output that cites canonical memory (FR27).
 * Zod is the authoring source; JSON Schema is emitted to `schema/` for CI and Python.
 */
export const CitationEnvelopeSchema = z
  .object({
    schema_version: z.literal(CITATION_ENVELOPE_SCHEMA_VERSION),
    node_id: z.string().uuid(),
    graph_epoch: z.number().int().nonnegative(),
    evidence_span: evidenceSpanSchema,
    retrieval_phase: retrievalPhaseSchema,
    confidence_score: z.number().min(0).max(1),
    /** ISO 8601 timestamp string (RFC 3339 profile) — same regex as Python (citation.py:23). */
    signed_timestamp: z.string().regex(SIGNED_TIMESTAMP_RFC3339_REGEX, {
      message: "signed_timestamp must be an ISO 8601 / RFC 3339 string",
    }),
    supersession: citationSupersessionOverriddenSchema.optional(),
  })
  .superRefine((val, ctx) => {
    if (val.evidence_span.end < val.evidence_span.start) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "evidence_span.end must be >= evidence_span.start",
        path: ["evidence_span", "end"],
      });
    }
  });

export type CitationEnvelope = z.infer<typeof CitationEnvelopeSchema>;
