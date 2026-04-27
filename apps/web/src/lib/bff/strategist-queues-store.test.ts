import { describe, expect, it } from "vitest";

import {
  appendActionQueueItems,
  listActionQueue,
  mutateActionQueueItem,
  patchSolidificationRow,
  patchValidationRow,
  pushInMeetingAudit,
  snapshotInMeetingAudit,
} from "./strategist-queues-store";

/** Isolated tenant key so parallel test files do not share queue maps. */
const t = () => `test-tenant-${Math.random().toString(36).slice(2, 11)}`;

describe("strategist-queues-store", () => {
  it("mutates action queue claim → in_progress → resolved", () => {
    const tenantId = t();
    appendActionQueueItems(tenantId, [
      {
        id: "aq-test-1",
        priority: "P1",
        phase: "P2",
        description: "Fixture",
        status: "open",
        claimed_by: null,
        updated_at: new Date().toISOString(),
      },
    ]);
    const open = listActionQueue(tenantId);
    expect(open).toHaveLength(1);
    expect(open[0]?.status).toBe("open");

    const claimed = mutateActionQueueItem(tenantId, "aq-test-1", {
      status: "claimed",
      claimed_by: "tester",
    });
    expect(claimed?.status).toBe("claimed");

    mutateActionQueueItem(tenantId, "aq-test-1", { status: "in_progress" });
    mutateActionQueueItem(tenantId, "aq-test-1", { status: "resolved" });
    const done = listActionQueue(tenantId).find((x) => x.id === "aq-test-1");
    expect(done?.status).toBe("resolved");
  });

  it("carryover-style rows preserve source in_meeting_alert", () => {
    const tenantId = t();
    appendActionQueueItems(tenantId, [
      {
        id: "carry-node-1",
        priority: "P2",
        phase: "P3",
        description: "From meeting",
        status: "open",
        claimed_by: null,
        updated_at: new Date().toISOString(),
        source: "in_meeting_alert",
        evidence_node_ids: ["2d4437ee-9336-441e-ab57-121b81ee57a4"],
      },
    ]);
    const rows = listActionQueue(tenantId);
    const row = rows.find((r) => r.id === "carry-node-1");
    expect(row?.source).toBe("in_meeting_alert");
    expect(row?.evidence_node_ids).toEqual(["2d4437ee-9336-441e-ab57-121b81ee57a4"]);
  });

  it("patches validation and solidification rows", () => {
    const tenantId = t();
    listActionQueue(tenantId);
    const v = patchValidationRow(tenantId, "vq-1", "resolved");
    expect(v?.state).toBe("resolved");
    const s = patchSolidificationRow(tenantId, "sq-1", "in-review");
    expect(s?.state).toBe("in-review");
  });

  it("records in-meeting audit events", () => {
    const tenantId = t();
    const before = snapshotInMeetingAudit().length;
    pushInMeetingAudit(tenantId, { type: "alert.dismissed", itemId: "chip-1" });
    const after = snapshotInMeetingAudit();
    expect(after.length).toBeGreaterThanOrEqual(before + 1);
    const last = after[after.length - 1];
    expect(last?.type).toBe("alert.dismissed");
    expect(last?.itemId).toBe("chip-1");
  });
});
