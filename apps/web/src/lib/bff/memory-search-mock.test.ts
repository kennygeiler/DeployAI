import { describe, expect, it } from "vitest";

import { searchMemoryMock } from "./memory-search-mock";
import {
  FIXTURE_DIGEST_TOP,
  FIXTURE_PHASE_ROWS,
} from "@/lib/strategist-data/surface-test-fixtures";

describe("searchMemoryMock", () => {
  it("matches digest label text", () => {
    const h = searchMemoryMock("Program risks", FIXTURE_DIGEST_TOP, FIXTURE_PHASE_ROWS);
    expect(h.some((x) => x.kind === "digest" && x.id === FIXTURE_DIGEST_TOP[0]!.id)).toBe(true);
  });

  it("matches action queue title", () => {
    const h = searchMemoryMock("pilot exit", FIXTURE_DIGEST_TOP, FIXTURE_PHASE_ROWS);
    expect(h.some((x) => x.kind === "action_queue")).toBe(true);
  });
});
