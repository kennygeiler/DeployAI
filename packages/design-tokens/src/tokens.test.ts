/**
 * WCAG AA (and AAA where spec demands) contrast assertions for every token
 * pair the design system uses for body text or chips.
 *
 * WCAG 2.1 SC 1.4.3 (Contrast Minimum):
 *   - Body text: ≥ 4.5:1
 *   - Large text (≥ 18pt / 14pt bold): ≥ 3:1
 *   - UI components & graphics (SC 1.4.11): ≥ 3:1
 *   - Inactive / disabled controls: exempt
 *
 * WCAG 2.1 SC 1.4.6 (Contrast Enhanced / AAA):
 *   - Body text: ≥ 7:1
 *
 * The DeployAI palette places `CitationChip` at AAA (spec line 856 of
 * ux-design-specification.md). `ink-400` is a disabled/placeholder color
 * per spec line 441 and is explicitly excluded from the body-text set.
 */

import { describe, expect, it } from "vitest";
import { hex } from "wcag-contrast";

import { destructive, evidence, ink, nullState, paper, signal } from "./colors.js";

const AA_BODY = 4.5;
const AA_LARGE_OR_UI = 3.0;
const AAA_BODY = 7.0;

type Pair = {
  readonly name: string;
  readonly fg: string;
  readonly bg: string;
};

function ratio(fg: string, bg: string): number {
  return hex(fg, bg);
}

describe("body-text pairs must meet WCAG AA (≥ 4.5:1) on paper-100", () => {
  const pairs: Pair[] = [
    { name: "ink-950 / paper-100", fg: ink[950], bg: paper[100] },
    { name: "ink-800 / paper-100", fg: ink[800], bg: paper[100] },
    { name: "ink-600 / paper-100", fg: ink[600], bg: paper[100] },
    { name: "evidence-700 / paper-100", fg: evidence[700], bg: paper[100] },
    { name: "signal-700 / paper-100", fg: signal[700], bg: paper[100] },
    { name: "null-600 / paper-100", fg: nullState[600], bg: paper[100] },
    { name: "destructive-700 / paper-100", fg: destructive[700], bg: paper[100] },
  ];

  it.each(pairs)("$name ≥ $expected:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_BODY);
  });
});

describe("chip pairs (colored label on tinted fill) must meet WCAG AA", () => {
  const pairs: Pair[] = [
    { name: "evidence-700 / evidence-100", fg: evidence[700], bg: evidence[100] },
    { name: "signal-700 / signal-100", fg: signal[700], bg: signal[100] },
    { name: "null-600 / null-100", fg: nullState[600], bg: nullState[100] },
    { name: "destructive-700 / destructive-100", fg: destructive[700], bg: destructive[100] },
  ];

  it.each(pairs)("$name ≥ 4.5:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_BODY);
  });
});

describe("inverted chip pairs (paper label on solid fill) must meet WCAG AA", () => {
  const pairs: Pair[] = [
    { name: "paper-100 / evidence-700", fg: paper[100], bg: evidence[700] },
    { name: "paper-100 / destructive-700", fg: paper[100], bg: destructive[700] },
  ];

  it.each(pairs)("$name ≥ 4.5:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_BODY);
  });
});

describe("AAA targets (CitationChip, primary text) must meet ≥ 7:1", () => {
  it("ink-950 / paper-100 reaches AAA", () => {
    expect(ratio(ink[950], paper[100])).toBeGreaterThanOrEqual(AAA_BODY);
  });

  it("evidence-700 / paper-100 reaches AAA (CitationChip target)", () => {
    expect(ratio(evidence[700], paper[100])).toBeGreaterThanOrEqual(AAA_BODY);
  });
});

describe("disabled / placeholder (ink-400) is WCAG-exempt from 4.5:1 but must clear the UI-component floor (≥ 3:1)", () => {
  it("ink-400 / paper-100 ≥ 3:1", () => {
    // ink-400 is explicitly disabled/placeholder (spec line 441). WCAG 2.1 SC 1.4.3
    // exempts inactive UI components; we still enforce SC 1.4.11 (≥ 3:1) as a floor.
    expect(ratio(ink[400], paper[100])).toBeGreaterThanOrEqual(AA_LARGE_OR_UI);
  });
});

describe("large-text / non-text contrast (≥ 3:1) for the evidence hover state", () => {
  it("evidence-600 / paper-100 ≥ 3:1 (non-text UI — hover fill)", () => {
    expect(ratio(evidence[600], paper[100])).toBeGreaterThanOrEqual(AA_LARGE_OR_UI);
  });
});
