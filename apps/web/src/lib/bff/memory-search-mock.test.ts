import { describe, expect, it } from "vitest";

import { searchMemoryMock } from "./memory-search-mock";
import { MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";

describe("searchMemoryMock", () => {
  it("finds digest by label token", () => {
    const h = searchMemoryMock("Program risks", MORNING_DIGEST_TOP, "2026-04-24");
    expect(h.some((x) => x.id === "2d4437ee-9336-441e-ab57-121b81ee57a4")).toBe(true);
  });

  it("finds action queue row", () => {
    const h = searchMemoryMock("pilot exit", MORNING_DIGEST_TOP, "2026-04-24");
    expect(h.some((x) => x.kind === "action_queue" && x.id === "aq-1")).toBe(true);
  });
});
