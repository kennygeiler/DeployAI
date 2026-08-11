import { describe, expect, it } from "vitest";
import { CitationEnvelopeSchema } from "../src/citation-envelope.js";

const valid = {
  schema_version: "0.1.0" as const,
  node_id: "550e8400-e29b-41d4-a716-446655440000",
  graph_epoch: 0,
  evidence_span: { start: 0, end: 10, source_ref: "urn:transcript#123" },
  retrieval_phase: "oracle" as const,
  confidence_score: 0.88,
  signed_timestamp: "2026-04-23T12:00:00.000Z",
};

describe("CitationEnvelopeSchema (v0.1.0)", () => {
  it("accepts a well-formed payload", () => {
    const r = CitationEnvelopeSchema.safeParse(valid);
    expect(r.success).toBe(true);
  });

  it("rejects when a required field is missing", () => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { node_id, ...noNode } = valid;
    const r = CitationEnvelopeSchema.safeParse(noNode);
    expect(r.success).toBe(false);
  });

  it("rejects malformed evidence_span (end < start)", () => {
    const r = CitationEnvelopeSchema.safeParse({
      ...valid,
      evidence_span: { start: 10, end: 0, source_ref: "x" },
    });
    expect(r.success).toBe(false);
  });

  it("rejects confidence_score outside [0, 1]", () => {
    const r = CitationEnvelopeSchema.safeParse({ ...valid, confidence_score: 1.1 });
    expect(r.success).toBe(false);
  });

  it("rejects unknown retrieval_phase", () => {
    const r = CitationEnvelopeSchema.safeParse({ ...valid, retrieval_phase: "nope" });
    expect(r.success).toBe(false);
  });

  it("accepts optional supersession (Epic 10.3)", () => {
    const r = CitationEnvelopeSchema.safeParse({
      ...valid,
      supersession: {
        type: "overridden" as const,
        override_event_id: "550e8400-e29b-41d4-a716-446655440001",
        overriding_evidence_event_ids: ["550e8400-e29b-41d4-a716-446655440002"],
      },
    });
    expect(r.success).toBe(true);
  });

  // --- signed_timestamp RFC 3339 fixtures (ticket B6) ---
  // Keep these strings identical to the fixtures in
  // services/_shared/citation/tests/test_citation.py so regex drift between
  // citation-envelope.ts and citation.py fails BOTH test suites.
  const validSignedTimestamps = [
    "2026-08-11T12:00:00Z",
    "2026-08-11T12:00:00.123Z",
    "2026-08-11T12:00:00+02:00",
    "2026-08-11T12:00:00.5-07:00",
  ];
  const invalidSignedTimestamps = [
    "yesterday",
    "2026-08-11", // date only
    "2026-08-11T12:00:00", // missing timezone
    "",
  ];

  it.each(validSignedTimestamps)("accepts RFC 3339 signed_timestamp %s", (ts) => {
    const r = CitationEnvelopeSchema.safeParse({ ...valid, signed_timestamp: ts });
    expect(r.success).toBe(true);
  });

  it.each(invalidSignedTimestamps)("rejects non-RFC 3339 signed_timestamp %j", (ts) => {
    const r = CitationEnvelopeSchema.safeParse({ ...valid, signed_timestamp: ts });
    expect(r.success).toBe(false);
  });
});
