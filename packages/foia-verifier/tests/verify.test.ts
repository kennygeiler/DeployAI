import { describe, expect, it } from "vitest";
import { verifyTsrStub } from "../src/verify.js";

describe("verifyTsrStub", () => {
  it("accepts a stub TSR for the echoed digest", () => {
    const p = new TextEncoder().encode("DEPLOYAI-TSA-STUB\0");
    const d = new Uint8Array(32);
    d.fill(7);
    const tsr = new Uint8Array(p.length + d.length);
    tsr.set(p, 0);
    tsr.set(d, p.length);
    const r = verifyTsrStub(tsr, d);
    expect(r.ok).toBe(true);
  });
});
