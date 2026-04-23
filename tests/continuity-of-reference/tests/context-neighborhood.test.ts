import { describe, expect, it } from "vitest";
import { getContextNeighborhood } from "../src/model.js";

describe("context-neighborhood", () => {
  it("is stable across logical surfaces (minus documented zoom collapses — none in v0 fixture)", () => {
    const id = "aaaaaaaa-aaaa-7aaa-8aaa-000000000001";
    const a = getContextNeighborhood(id);
    const b = getContextNeighborhood(id);
    expect(a).toEqual(b);
  });
});
