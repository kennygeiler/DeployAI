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
    /** ISO 8601 timestamp string (RFC 3339 profile). */
    signed_timestamp: z.string().min(1),
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
