import { describe, expect, it } from "vitest";

import {
  getStrategistEvidenceByNodeId,
  MORNING_DIGEST_TOP,
  PHASE_TRACKING_ROWS,
} from "./mock-digest";

describe("getStrategistEvidenceByNodeId", () => {
  it("returns the same digest catalog row for every digest id (Story 1.12 + FR41 continuity)", () => {
    for (const row of MORNING_DIGEST_TOP) {
      expect(getStrategistEvidenceByNodeId(row.id)).toBe(row);
    }
  });

  it("resolves digest citation ids", () => {
    const id = MORNING_DIGEST_TOP[0]!.id;
    const row = getStrategistEvidenceByNodeId(id);
    expect(row?.label).toContain("Program risks");
  });

  it("resolves action-queue ids", () => {
    const id = PHASE_TRACKING_ROWS[0]!.id;
    const row = getStrategistEvidenceByNodeId(id);
    expect(row?.label).toContain("pilot exit");
  });

  it("bridges action-queue rows to digest-shaped evidence with aligned ids and body (FR41)", () => {
    const aq = PHASE_TRACKING_ROWS[0]!;
    const row = getStrategistEvidenceByNodeId(aq.id);
    expect(row).not.toBeNull();
    expect(row!.id).toBe(aq.id);
    expect(row!.label).toBe(aq.title);
    expect(row!.preview).toEqual({
      citationId: aq.id,
      retrievalPhase: `${aq.phase} (action)`,
      confidence: "—",
      signedTimestamp: aq.metadata.timestamp,
    });
    expect(row!.retrievalPhase).toBe(aq.retrievalPhase);
    expect(row!.metadata).toEqual(aq.metadata);
    expect(row!.evidenceSpan).toEqual(aq.evidenceSpan);
    expect(row!.bodyText).toBe(`${aq.summary}\n\n${aq.bodyText}`);
    expect(row!.state).toBe("loaded");
  });

  it("returns null for unknown id", () => {
    expect(getStrategistEvidenceByNodeId("00000000-0000-0000-0000-000000000000")).toBeNull();
  });
});
