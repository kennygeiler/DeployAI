import { describe, expect, it } from "vitest";
import { applyNodeState, getStateVersion, resolveNode } from "../src/model.js";

describe("state-propagation", () => {
  it("applies state to every surface view in one update", () => {
    const id = "bbbbbbbb-bbbb-7bbb-8bbb-000000000001";
    const v0 = getStateVersion();
    applyNodeState(id, "tombstoned");
    expect(getStateVersion()).toBe(v0 + 1);
    expect(resolveNode(id, "digest")?.state).toBe("tombstoned");
    expect(resolveNode(id, "alert")?.state).toBe("tombstoned");
  });
});
