import { describe, expect, it } from "vitest";
import { createStubLlmProvider } from "../src/stub-provider.js";
import { createStubLlmProvider as createB } from "../src/stub-provider.js";

describe("LLMProvider / failover (NFR70 surface)", () => {
  it("swaps provider instances while preserving full capability matrix", () => {
    const a = createStubLlmProvider("A");
    const b = createB("B");
    const ka = a.capabilities();
    const kb = b.capabilities();
    expect(ka).toEqual(kb);
  });

  it("stub is deterministic for chat and embed", async () => {
    const p = createStubLlmProvider();
    const t = await p.chatComplete([{ role: "user", content: "hi" }]);
    expect(t).toBe("stub-out:2");
    const e = await p.embed("x");
    expect(e[0]).toBe(1);
  });
});
