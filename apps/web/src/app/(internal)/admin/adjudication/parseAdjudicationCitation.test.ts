import { describe, expect, it } from "vitest";

import {
  ADJ_EVIDENCE_BODY_MAX_CHARS,
  parseAdjudicationCitation,
} from "./parseAdjudicationCitation";

const validEnvelope = {
  schema_version: "0.1.0" as const,
  node_id: "550e8400-e29b-41d4-a716-446655440000",
  graph_epoch: 0,
  evidence_span: { start: 0, end: 10, source_ref: "urn:transcript#123" },
  retrieval_phase: "oracle" as const,
  confidence_score: 0.88,
  signed_timestamp: "2026-04-23T12:00:00.000Z",
};

describe("parseAdjudicationCitation", () => {
  it("returns null when meta is empty", () => {
    expect(parseAdjudicationCitation({})).toBeNull();
  });

  it("returns null when citation_envelope is missing", () => {
    expect(parseAdjudicationCitation({ other: 1 })).toBeNull();
  });

  it("maps a valid citation_envelope", () => {
    const r = parseAdjudicationCitation({
      citation_envelope: validEnvelope,
      evidence_body: "Hello world",
    });
    expect(r).not.toBeNull();
    expect(r!.preview.citationId).toBe("550e8400-e29b-41d4-a716-446655440000");
    expect(r!.preview.retrievalPhase).toBe("oracle");
    expect(r!.retrievalPhase).toBe("oracle");
    expect(r!.bodyText).toBe("Hello world");
    expect(r!.panelMetadata.sourceType).toBe("urn:transcript#123");
    expect(r!.evidenceSpan.start).toBe(0);
    expect(r!.evidenceSpan.end).toBe(10);
  });

  it("returns null for invalid envelope", () => {
    expect(
      parseAdjudicationCitation({
        citation_envelope: { ...validEnvelope, node_id: "not-a-uuid" },
      }),
    ).toBeNull();
  });

  it("applies metadata overrides", () => {
    const r = parseAdjudicationCitation({
      citation_envelope: validEnvelope,
      citation_label: "  Transcript  ",
      citation_supersession: "superseded",
      citation_supersession_detail: "Newer run",
    });
    expect(r).not.toBeNull();
    expect(r!.chipLabel).toBe("Transcript");
    expect(r!.panelMetadata.supersession).toBe("superseded");
    expect(r!.panelMetadata.supersessionDetail).toBe("Newer run");
  });

  it("truncates evidence_body at ADJ_EVIDENCE_BODY_MAX_CHARS", () => {
    const long = "x".repeat(ADJ_EVIDENCE_BODY_MAX_CHARS + 50);
    const r = parseAdjudicationCitation({
      citation_envelope: validEnvelope,
      evidence_body: long,
    });
    expect(r!.bodyText).toHaveLength(ADJ_EVIDENCE_BODY_MAX_CHARS);
  });
});
