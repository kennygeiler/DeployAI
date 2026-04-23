import { describe, expect, it } from "vitest";
import { assertOnlyDesignTokens, citationChipStyle } from "../src/citation-chip-style.js";

describe("visual-token parity", () => {
  it("CitationChip-style object uses only deployai design CSS variables", () => {
    const s = citationChipStyle();
    expect(() => assertOnlyDesignTokens(s)).not.toThrow();
  });
});
