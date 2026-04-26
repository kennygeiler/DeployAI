import { describe, expect, it } from "vitest";

import { getStrategistEvidenceByNodeId, MORNING_DIGEST_TOP, PHASE_TRACKING_ROWS } from "./mock-digest";

describe("getStrategistEvidenceByNodeId", () => {
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

  it("returns null for unknown id", () => {
    expect(getStrategistEvidenceByNodeId("00000000-0000-0000-0000-000000000000")).toBeNull();
  });
});
