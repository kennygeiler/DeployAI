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
});
