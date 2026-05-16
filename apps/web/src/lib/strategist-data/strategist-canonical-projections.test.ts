import { afterEach, describe, expect, it } from "vitest";

import { strategistCanonicalProjectionsStubFlagEnabled } from "./strategist-canonical-projections";

describe("strategistCanonicalProjectionsStubFlagEnabled", () => {
  const original = process.env.DEPLOYAI_STRATEGIST_CANONICAL_PROJECTIONS_STUB;

  afterEach(() => {
    if (original === undefined) {
      delete process.env.DEPLOYAI_STRATEGIST_CANONICAL_PROJECTIONS_STUB;
    } else {
      process.env.DEPLOYAI_STRATEGIST_CANONICAL_PROJECTIONS_STUB = original;
    }
  });

  it("is false when unset", () => {
    delete process.env.DEPLOYAI_STRATEGIST_CANONICAL_PROJECTIONS_STUB;
    expect(strategistCanonicalProjectionsStubFlagEnabled()).toBe(false);
  });

  it("is true when set to 1", () => {
    process.env.DEPLOYAI_STRATEGIST_CANONICAL_PROJECTIONS_STUB = "1";
    expect(strategistCanonicalProjectionsStubFlagEnabled()).toBe(true);
  });
});
