import { describe, expect, it } from "vitest";

import { BREAKPOINT_PX, MOBILE_READ_ONLY_PX } from "./breakpoints";

describe("breakpoints (UX-DR37 / UX-DR38)", () => {
  it("keeps mobile read-only aligned with md (Tailwind default < md:)", () => {
    expect(MOBILE_READ_ONLY_PX).toBe(768);
    expect(BREAKPOINT_PX.md).toBe(768);
    expect(MOBILE_READ_ONLY_PX).toBe(BREAKPOINT_PX.md);
  });

  it("exposes a stable sm→2xl map", () => {
    expect(BREAKPOINT_PX).toEqual({
      sm: 640,
      md: 768,
      lg: 1024,
      xl: 1280,
      "2xl": 1536,
    });
  });
});
