import { describe, expect, it } from "vitest";

import {
  buildInMeetingCarryoverRows,
  digestLabelForCarryoverId,
} from "./in-meeting-carryover-build";

describe("digestLabelForCarryoverId", () => {
  it("resolves digest top id", () => {
    expect(digestLabelForCarryoverId("2d4437ee-9336-441e-ab57-121b81ee57a4")).toBe(
      "07:00 — Program risks (DOT comms)",
    );
  });

  it("resolves ranked-out id with reason", () => {
    expect(digestLabelForCarryoverId("out-1")).toBe(
      "Low-signal: generic status email (Below confidence floor for digest)",
    );
  });

  it("returns undefined for unknown id", () => {
    expect(digestLabelForCarryoverId("unknown")).toBeUndefined();
  });
});

describe("buildInMeetingCarryoverRows", () => {
  it("builds stable unique ids and in_meeting_alert source", () => {
    const now = "2026-04-26T12:00:00.000Z";
    const rows = buildInMeetingCarryoverRows(["a", "b"], now);
    expect(rows).toHaveLength(2);
    expect(rows[0]!.id).toBe(`carry-a-0-${now}`);
    expect(rows[1]!.id).toBe(`carry-b-1-${now}`);
    expect(rows[0]!.source).toBe("in_meeting_alert");
    expect(rows[0]!.status).toBe("open");
    expect(rows[0]!.evidence_node_ids).toEqual(["a"]);
  });

  it("uses fallback description when id is unknown", () => {
    const now = "2026-04-26T12:00:00.000Z";
    const rows = buildInMeetingCarryoverRows(["x"], now);
    expect(rows[0]!.description).toBe("Carryover from in-meeting alert (x)");
  });
});
