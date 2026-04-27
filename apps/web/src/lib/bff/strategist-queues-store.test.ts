import { describe, expect, it } from "vitest";

import {
  appendActionQueueItems,
  listActionQueue,
  listSolidificationQueue,
  listValidationQueue,
  mutateActionQueueItem,
  patchSolidificationRow,
  patchValidationRow,
  pushActionQueueAudit,
  pushInMeetingAudit,
  pushSolidificationAudit,
  pushValidationAudit,
  seedStrategistQueuesIfEmpty,
  snapshotActionQueueAudit,
  snapshotInMeetingAudit,
  snapshotSolidificationAudit,
  snapshotValidationAudit,
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
    mutateActionQueueItem(tenantId, "aq-test-1", {
      status: "resolved",
      resolution_reason: "done",
      evidence_event_ids: ["ev-1"],
    });
    const done = listActionQueue(tenantId).find((x) => x.id === "aq-test-1");
    expect(done?.status).toBe("resolved");
    expect(done?.resolution_reason).toBe("done");
    expect(done?.evidence_event_ids).toEqual(["ev-1"]);
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

  it("patches validation and solidification rows in backing store", () => {
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

  it("Epic 9.5 — action queue audit snapshots", () => {
    const tenantId = t();
    const n = snapshotActionQueueAudit().length;
    pushActionQueueAudit(tenantId, "action_queue.claimed", { itemId: "x" });
    expect(snapshotActionQueueAudit().length).toBeGreaterThanOrEqual(n + 1);
  });

  it("Epic 9.6 — ten validation seeds; confirm/modify/reject/defer drops resolved from list", () => {
    const tenantId = t();
    seedStrategistQueuesIfEmpty(tenantId);
    expect(listValidationQueue(tenantId)).toHaveLength(10);
    for (let i = 1; i <= 5; i++) {
      patchValidationRow(tenantId, `vq-${i}`, "resolved");
    }
    expect(listValidationQueue(tenantId)).toHaveLength(5);
    for (let i = 6; i <= 8; i++) {
      patchValidationRow(tenantId, `vq-${i}`, "resolved");
    }
    expect(listValidationQueue(tenantId)).toHaveLength(2);
    patchValidationRow(tenantId, "vq-9", "resolved");
    patchValidationRow(tenantId, "vq-10", "resolved");
    expect(listValidationQueue(tenantId)).toHaveLength(0);
  });

  it("Epic 9.6 — validation audit kinds differ for modify vs reject", () => {
    const tenantId = t();
    const before = snapshotValidationAudit().length;
    pushValidationAudit(tenantId, "validation.modified", { id: "a", reason: "r1" });
    pushValidationAudit(tenantId, "validation.rejected", { id: "b", reason: "r2" });
    const snap = snapshotValidationAudit();
    expect(snap.length).toBeGreaterThanOrEqual(before + 2);
    expect(snap[snap.length - 2]?.kind).toBe("validation.modified");
    expect(snap[snap.length - 1]?.kind).toBe("validation.rejected");
  });

  it("Epic 9.7 — twenty solidification seeds; promote/demote remove from active list, defer stays", () => {
    const tenantId = t();
    seedStrategistQueuesIfEmpty(tenantId);
    expect(listSolidificationQueue(tenantId)).toHaveLength(20);
    for (let i = 1; i <= 10; i++) {
      patchSolidificationRow(tenantId, `sq-${i}`, "resolved");
    }
    expect(listSolidificationQueue(tenantId)).toHaveLength(10);
    for (let i = 11; i <= 15; i++) {
      patchSolidificationRow(tenantId, `sq-${i}`, "escalated");
    }
    expect(listSolidificationQueue(tenantId)).toHaveLength(5);
    for (let i = 16; i <= 20; i++) {
      patchSolidificationRow(tenantId, `sq-${i}`, "in-review");
    }
    expect(listSolidificationQueue(tenantId)).toHaveLength(5);
    pushSolidificationAudit(tenantId, "solidification.promoted", { id: "sq-16" });
    expect(snapshotSolidificationAudit().length).toBeGreaterThanOrEqual(1);
  });
});
