import { describe, expect, it } from "vitest";

import { cn } from "@/lib/utils";

describe("cn radius merging", () => {
  it("token radii replace the base radius instead of coexisting with it", () => {
    // Regression: rounded-card must dedupe against rounded-full — with stock
    // tailwind-merge both classes survive and stylesheet order wins.
    expect(cn("rounded-full", "rounded-card")).toBe("rounded-card");
    expect(cn("rounded-md", "rounded-control")).toBe("rounded-control");
    expect(cn("rounded-card", "rounded-full")).toBe("rounded-full");
  });

  it("keeps normal merging behavior", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
    expect(cn("text-sm", "font-medium")).toBe("text-sm font-medium");
  });
});
