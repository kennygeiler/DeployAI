import { describe, expect, it } from "vitest";
import { resolveNode, type SurfaceId } from "../src/model.js";

const surfaces: SurfaceId[] = ["digest", "alert", "phase", "adjudication"];
const id = "aaaaaaaa-aaaa-7aaa-8aaa-000000000001";

describe("same-node-resolution", () => {
  it("returns identical canonical data for every surface", () => {
    const ref = resolveNode(id, "digest");
    expect(ref).toBeDefined();
    for (const s of surfaces) {
      expect(resolveNode(id, s)).toEqual(ref);
    }
  });
});
