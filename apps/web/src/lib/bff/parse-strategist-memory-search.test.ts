import { describe, expect, it } from "vitest";

import { parseStrategistMemorySearchResponse } from "./parse-strategist-memory-search";

describe("parseStrategistMemorySearchResponse", () => {
  it("parses BFF mock shape", () => {
    const p = parseStrategistMemorySearchResponse({
      source: "mock",
      hits: [{ id: "a1", label: "L", kind: "digest", queryText: "x" }],
    });
    expect(p.source).toBe("mock");
    expect(p.hits).toHaveLength(1);
    expect(p.hits[0]?.id).toBe("a1");
  });

  it("accepts results alias", () => {
    const p = parseStrategistMemorySearchResponse({
      source: "remote",
      results: [{ id: "b2", label: "R", kind: "action_queue", queryText: "y" }],
    });
    expect(p.hits[0]?.kind).toBe("action_queue");
  });
});
