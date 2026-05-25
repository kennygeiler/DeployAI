import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { cpEmitAuditEventMock } = vi.hoisted(() => ({ cpEmitAuditEventMock: vi.fn() }));

vi.mock("@/lib/internal/audit-cp", () => ({
  cpEmitAuditEvent: cpEmitAuditEventMock,
}));

import { emitTenantAuditEventBackground } from "@/lib/internal/audit-emit";

describe("emitTenantAuditEventBackground", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    cpEmitAuditEventMock.mockReset();
    cpEmitAuditEventMock.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("skips emission when actorId is null", () => {
    emitTenantAuditEventBackground("t1", null, "cat", "sum", {});
    vi.runAllTimers();
    expect(cpEmitAuditEventMock).not.toHaveBeenCalled();
  });

  it("skips emission when actorId is not a UUID", () => {
    emitTenantAuditEventBackground("t1", "not-a-uuid", "cat", "sum", {});
    vi.runAllTimers();
    expect(cpEmitAuditEventMock).not.toHaveBeenCalled();
  });

  it("fires emission when actorId is a UUID", () => {
    const actor = "11111111-2222-4333-8444-555566667777";
    emitTenantAuditEventBackground(
      "t1",
      actor,
      "tenant.webhook.created",
      "created webhook",
      { webhook_id: "w1" },
      "w1",
    );
    vi.runAllTimers();
    expect(cpEmitAuditEventMock).toHaveBeenCalledTimes(1);
    expect(cpEmitAuditEventMock).toHaveBeenCalledWith("t1", {
      actor_id: actor,
      category: "tenant.webhook.created",
      summary: "created webhook",
      detail: { webhook_id: "w1" },
      ref_id: "w1",
    });
  });

  it("defaults ref_id to null when omitted", () => {
    const actor = "11111111-2222-4333-8444-555566667777";
    emitTenantAuditEventBackground("t1", actor, "cat", "sum", {});
    vi.runAllTimers();
    expect(cpEmitAuditEventMock).toHaveBeenCalledWith(
      "t1",
      expect.objectContaining({ ref_id: null }),
    );
  });

  it("does not throw when cpEmitAuditEvent rejects", async () => {
    cpEmitAuditEventMock.mockRejectedValueOnce(new Error("boom"));
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const actor = "11111111-2222-4333-8444-555566667777";
    expect(() => emitTenantAuditEventBackground("t1", actor, "cat", "sum", {})).not.toThrow();
    await vi.runAllTimersAsync();
    expect(errSpy).toHaveBeenCalledWith("[audit-emit] failed", expect.any(Error));
    errSpy.mockRestore();
  });
});
