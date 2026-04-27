import { describe, expect, it } from "vitest";

import { splitPrimaryAndRankedOut } from "./three-item-budget";

describe("splitPrimaryAndRankedOut", () => {
  it("keeps at most three primary items (Epic 9.2)", () => {
    const items = [1, 2, 3, 4, 5];
    const { primary, rankedOut } = splitPrimaryAndRankedOut(items, 3);
    expect(primary.length).toBeLessThanOrEqual(3);
    expect(primary).toEqual([1, 2, 3]);
    expect(rankedOut).toEqual([4, 5]);
  });
});
