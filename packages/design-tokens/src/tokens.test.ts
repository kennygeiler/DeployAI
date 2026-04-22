/**
 * WCAG AA (and AAA where spec demands) contrast assertions for every token
 * pair the design system uses for body text, chips, card surfaces, and
 * non-text UI components.
 *
 * WCAG 2.1 SC 1.4.3 (Contrast Minimum):
 *   - Body text: ≥ 4.5:1
 *   - Large text (≥ 18pt / 14pt bold): ≥ 3:1
 *   - UI components & graphics (SC 1.4.11): ≥ 3:1
 *
 * WCAG 2.1 SC 1.4.6 (Contrast Enhanced / AAA):
 *   - Body text: ≥ 7:1
 *
 * The DeployAI palette places `CitationChip` at AAA (spec line 856 of
 * ux-design-specification.md). `ink-400` is used for disabled + placeholder
 * text; per AC3 it must still clear AA (4.5:1) against paper-100 because
 * placeholder text is not WCAG-exempt.
 */

import { describe, expect, it } from "vitest";
import { hex } from "wcag-contrast";

import { destructive, evidence, ink, nullState, paper, signal, stone } from "./colors.js";

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
    { name: "ink-400 / paper-100 (disabled + placeholder)", fg: ink[400], bg: paper[100] },
    { name: "evidence-700 / paper-100", fg: evidence[700], bg: paper[100] },
    { name: "signal-700 / paper-100", fg: signal[700], bg: paper[100] },
    { name: "null-600 / paper-100", fg: nullState[600], bg: paper[100] },
    { name: "destructive-700 / paper-100", fg: destructive[700], bg: paper[100] },
  ];

  it.each(pairs)("$name ≥ 4.5:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_BODY);
  });
});

describe("card-surface body-text pairs must meet WCAG AA on paper-200/300", () => {
  const pairs: Pair[] = [
    { name: "ink-950 / paper-200", fg: ink[950], bg: paper[200] },
    { name: "ink-800 / paper-200", fg: ink[800], bg: paper[200] },
    { name: "ink-600 / paper-200", fg: ink[600], bg: paper[200] },
    { name: "ink-950 / paper-300", fg: ink[950], bg: paper[300] },
    { name: "ink-800 / paper-300", fg: ink[800], bg: paper[300] },
  ];

  it.each(pairs)("$name ≥ 4.5:1", ({ fg, bg }) => {
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
    { name: "paper-100 / signal-700", fg: paper[100], bg: signal[700] },
    { name: "paper-100 / null-600", fg: paper[100], bg: nullState[600] },
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

describe("non-text UI components must meet WCAG SC 1.4.11 (≥ 3:1)", () => {
  // Note: paper-400 is decorative-only (pure visual divider, WCAG-exempt per
  // SC 1.4.11 "Understanding"). Any actionable UI chrome (form borders, focus
  // rings, toggles) MUST use stone-500 or darker — this suite enforces that
  // contract by covering every token the UX spec marks as interactive-border.
  const pairs: Pair[] = [
    { name: "stone-500 / paper-100 (form-field border)", fg: stone[500], bg: paper[100] },
    { name: "evidence-600 / paper-100 (hover fill)", fg: evidence[600], bg: paper[100] },
  ];

  it.each(pairs)("$name ≥ 3:1", ({ fg, bg }) => {
    expect(ratio(fg, bg)).toBeGreaterThanOrEqual(AA_LARGE_OR_UI);
  });
});
